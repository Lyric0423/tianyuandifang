"""双轴半步驱动、同步插补和抬笔。没有限位开关，不执行撞边回零。"""
import math
import time
from machine import Pin, PWM
import config as C
from geometry import circle, square, checked_targets, dda

HALFSTEP = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
            (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1))


class Axis:
    def __init__(self, pins, direction):
        if direction not in (-1, 1):
            raise ValueError("axis direction must be +/-1")
        self.pins = [Pin(pin, Pin.OUT, value=0) for pin in pins]
        self.direction = direction
        self.phase = 0
        self.steps = 0

    def step(self, logical_direction):
        self.phase = (self.phase + logical_direction * self.direction) % 8
        for pin, value in zip(self.pins, HALFSTEP[self.phase]):
            pin.value(value)
        self.steps += logical_direction

    def release(self):
        for pin in self.pins:
            pin.value(0)


class Plotter:
    def __init__(self):
        self.x = Axis(C.X_PINS, C.X_DIRECTION)
        self.y = Axis(C.Y_PINS, C.Y_DIRECTION)
        self.servo = PWM(Pin(C.SERVO_PIN), freq=50)
        self.referenced = False
        self.pen_is_down = False
        self._run_started = None
        self.pen_up()

    def pulse(self, microseconds):
        value = int(microseconds)
        if not C.SERVO_MIN_US <= value <= C.SERVO_MAX_US:
            raise ValueError("servo pulse outside configured range")
        # duty_u16 是 0..65535；50 Hz 周期为 20000 us。
        self.servo.duty_u16(round(value * 65535 / 20000))
        time.sleep_ms(C.SERVO_SETTLE_MS)

    def pen_up(self):
        self.pulse(C.SERVO_UP_US)
        self.pen_is_down = False

    def pen_down(self):
        self.pulse(C.SERVO_DOWN_US)
        self.pen_is_down = True

    def set_origin(self):
        self.pen_up()
        self.x.steps = self.y.steps = 0
        self.referenced = True

    def position(self):
        return (self.x.steps / C.X_STEPS_PER_MM,
                self.y.steps / C.Y_STEPS_PER_MM)

    def _deadline(self):
        if self._run_started is not None:
            elapsed = time.ticks_diff(time.ticks_ms(), self._run_started)
            if elapsed >= C.RUN_LIMIT_SECONDS * 1000:
                raise RuntimeError("run time budget exceeded")

    def _execute(self, targets, feed):
        if not 0 < feed <= 10:
            raise ValueError("feed must be in (0, 10] mm/s")
        start = (self.x.steps, self.y.steps)
        lengths = []
        previous = start
        for target in targets:
            lengths.append(math.sqrt(((target[0]-previous[0])/C.X_STEPS_PER_MM)**2
                                     + ((target[1]-previous[1])/C.Y_STEPS_PER_MM)**2))
            previous = target
        total = sum(lengths)
        done = 0.0
        previous = start
        due = time.ticks_us()
        for target, length in zip(targets, lengths):
            dx, dy = target[0]-previous[0], target[1]-previous[1]
            count = max(abs(dx), abs(dy))
            previous = target
            if count == 0:
                continue
            ds = length / count
            for step_x, step_y in dda(dx, dy):
                self._deadline()
                ramp_distance = max(0, min(done, total-done))
                speed = min(feed, math.sqrt(C.MIN_FEED**2
                                           + 2*C.ACCELERATION*ramp_distance))
                period = max(round(1_000_000 * ds / speed),
                             round(1_000_000 / C.MAX_HALFSTEPS_PER_SECOND))
                # 不在落后时瞬间补走多个半步，避免电脑/解释器延迟引起突跳。
                now = time.ticks_us()
                if time.ticks_diff(now, due) > period:
                    due = now
                due = time.ticks_add(due, period)
                wait = time.ticks_diff(due, time.ticks_us())
                if wait > 0:
                    time.sleep_us(wait)
                if step_x:
                    self.x.step(step_x)
                if step_y:
                    self.y.step(step_y)
                done += ds

    def move(self, x, y, feed=None):
        if not self.referenced:
            raise RuntimeError("set origin first: zero YES")
        targets = checked_targets([(x, y)], C.X_STEPS_PER_MM, C.Y_STEPS_PER_MM,
                                  C.WORK_X, C.WORK_Y)
        self._execute(targets, C.TRAVEL_FEED if feed is None else feed)

    def jog(self, axis, distance):
        if axis not in ("x", "y") or not math.isfinite(distance):
            raise ValueError("jog x|y distance")
        self.pen_up()
        if self.referenced:
            x, y = self.position()
            self.move(x + (distance if axis == "x" else 0),
                      y + (distance if axis == "y" else 0), C.JOG_FEED)
        else:
            if abs(distance) > C.MAX_UNREFERENCED_JOG:
                raise ValueError("before zero, jog at most 5 mm each time")
            tx = self.x.steps + (round(distance*C.X_STEPS_PER_MM) if axis == "x" else 0)
            ty = self.y.steps + (round(distance*C.Y_STEPS_PER_MM) if axis == "y" else 0)
            self._execute([(tx, ty)], C.JOG_FEED)

    def release(self):
        self.x.release()
        self.y.release()
        # 断励磁后滑台可能被外力移动，软件不能继续相信原点。
        self.referenced = False

    def emergency_stop(self):
        self._run_started = None
        try:
            self.pen_up()
        finally:
            self.release()

    def calibration(self, axis, distance=50.0):
        if axis not in ("x", "y") or not 0 < distance <= 50:
            raise ValueError("cal x|y [positive distance <=50]")
        if not self.referenced:
            raise RuntimeError("set origin first")
        # 先检查终点，检查失败时不能落笔或先移动。
        endpoint = (10+distance, 10) if axis == "x" else (10, 10+distance)
        checked_targets([endpoint], C.X_STEPS_PER_MM, C.Y_STEPS_PER_MM,
                        C.WORK_X, C.WORK_Y)
        try:
            self.pen_up()
            self.move(10, 10)
            self.pen_down()
            self.move(endpoint[0], endpoint[1], C.DRAW_FEED)
        finally:
            self.pen_up()

    def draw(self, dry=False):
        if not self.referenced:
            raise RuntimeError("set origin first: zero YES")
        circle_points = circle(C.CENTER, C.CIRCLE_RADIUS, C.CIRCLE_SEGMENTS)
        square_points = square(C.CENTER, C.SQUARE_SIDE)
        # 完整预检后才开始移动或落笔。
        circle_targets = checked_targets(circle_points, C.X_STEPS_PER_MM,
                                        C.Y_STEPS_PER_MM, C.WORK_X, C.WORK_Y)
        checked_targets(square_points, C.X_STEPS_PER_MM,
                        C.Y_STEPS_PER_MM, C.WORK_X, C.WORK_Y)
        self._run_started = time.ticks_ms()
        try:
            self.pen_up()
            self.move(*circle_points[0])
            if not dry:
                self.pen_down()
            self._execute(circle_targets[1:], C.DRAW_FEED)
            self.pen_up()
            self.move(*square_points[0])
            if not dry:
                self.pen_down()
            for x, y in square_points[1:]:
                self.move(x, y, C.DRAW_FEED)  # 每个方角停稳再换方向
            self.pen_up()
            self.move(0, 0)
            self._deadline()
        except BaseException:
            self.emergency_stop()
            raise
        finally:
            self._run_started = None
        self.release()
        print("Finished. Coils released; set origin again before the next run.")
