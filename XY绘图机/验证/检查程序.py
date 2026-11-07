#!/usr/bin/env python3
"""在电脑运行的功能验证。模拟 GPIO 和时间，不连接或驱动实物。"""
import sys
import json
import math
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "代码"))


class Pin:
    OUT = 1
    def __init__(self, number, mode=None, value=0):
        self.number, self.current = number, value
    def value(self, value=None):
        if value is not None:
            self.current = value
        return self.current


class PWM:
    def __init__(self, pin, freq=50):
        self.pin, self.freq, self.duty = pin, freq, 0
    def duty_u16(self, value):
        if not 0 <= value <= 65535:
            raise ValueError("bad duty")
        self.duty = value


fake_machine = types.ModuleType("machine")
fake_machine.Pin, fake_machine.PWM = Pin, PWM
sys.modules["machine"] = fake_machine
import config as C
import geometry as G
import plotter as P


class Clock:
    def __init__(self): self.us = 0
    def sleep_us(self, us): self.us += us
    def sleep_ms(self, ms): self.us += ms * 1000
    def ticks_us(self): return int(self.us) % (1 << 30)
    def ticks_ms(self): return int(self.us // 1000) % (1 << 30)
    def ticks_add(self, a, b): return (a + b) % (1 << 30)
    def ticks_diff(self, a, b): return (a-b+(1 << 29)) % (1 << 30) - (1 << 29)


REPORT = {"simulation_only": True, "hardware_verified": False}


class Tests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        P.time = self.clock
        self.p = P.Plotter()

    def test_dda_in_all_directions(self):
        for dx, dy in ((64,64),(100,37),(-100,37),(5,-81),(0,90),(-10,0),(0,0)):
            points = list(G.dda(dx,dy))
            self.assertEqual((sum(x for x,y in points),sum(y for x,y in points)),(dx,dy))
            self.assertEqual(len(points),max(abs(dx),abs(dy)))
            for x,y in points:self.assertLessEqual(max(abs(x),abs(y)),1)

    def test_reference_and_soft_limits(self):
        with self.assertRaises(RuntimeError):self.p.draw()
        with self.assertRaises(ValueError):self.p.jog("x",6)
        self.p.set_origin()
        before = self.p.position()
        for target in ((-1,0),(C.WORK_X+1,0),(0,float("nan"))):
            with self.assertRaises(ValueError):self.p.move(*target)
            self.assertEqual(self.p.position(),before)
        self.p.release()
        self.assertFalse(self.p.referenced)

    def test_full_draw_geometry_and_time(self):
        self.p.set_origin()
        trace=[]
        old_step=P.Axis.step
        def traced(axis,direction):
            old_step(axis,direction)
            trace.append((self.p.position(),self.p.pen_is_down))
        P.Axis.step=traced
        try:self.p.draw()
        finally:P.Axis.step=old_step
        groups=[]
        previous_down=False
        for point,down in trace:
            if down and not previous_down:groups.append([])
            if down:groups[-1].append(point)
            previous_down=down
            self.assertTrue(0<=point[0]<=C.WORK_X and 0<=point[1]<=C.WORK_Y)
        self.assertEqual(len(groups),2)
        radial_errors=[abs(math.hypot(x-C.CENTER[0],y-C.CENTER[1])-C.CIRCLE_RADIUS)
                       for x,y in groups[0]]
        self.assertLess(max(radial_errors),0.04)
        h=C.SQUARE_SIDE/2
        square_errors=[abs(max(abs(x-C.CENTER[0]),abs(y-C.CENTER[1]))-h)
                       for x,y in groups[1]]
        self.assertLess(max(square_errors),0.02)
        self.assertEqual(groups[0][-1],G.circle(C.CENTER,C.CIRCLE_RADIUS)[0])
        self.assertEqual(groups[1][-1],G.square(C.CENTER,C.SQUARE_SIDE)[0])
        self.assertEqual(self.p.position(),(0,0))
        self.assertFalse(self.p.pen_is_down)
        self.assertFalse(self.p.referenced)
        self.assertTrue(all(pin.value()==0 for axis in (self.p.x,self.p.y) for pin in axis.pins))
        elapsed=self.clock.us/1e6
        self.assertLess(elapsed,480)
        REPORT.update({"nominal_simulated_seconds_including_setup":round(elapsed,3),
            "circle_diameter_mm":C.CIRCLE_RADIUS*2,"square_side_mm":C.SQUARE_SIDE,
            "circle_max_quantization_radial_error_mm":round(max(radial_errors),6),
            "square_max_edge_error_mm":round(max(square_errors),6),
            "final_position_mm":self.p.position(),"pen_down_paths":2,
            "note":"时间未计入解释器/GPIO开销和实物卡顿；误差仅为指令量化误差，不是实物精度。"})

    def test_dry_run_never_lowers_pen(self):
        self.p.set_origin()
        def forbidden():raise AssertionError("dry lowered pen")
        self.p.pen_down=forbidden
        self.p.draw(dry=True)
        self.assertEqual(self.p.position(),(0,0))

    def test_oversized_shape_rejected_before_motion(self):
        self.p.set_origin()
        radius=C.CIRCLE_RADIUS
        try:
            C.CIRCLE_RADIUS=100
            with self.assertRaises(ValueError):self.p.draw()
            self.assertEqual(self.p.position(),(0,0))
            self.assertFalse(self.p.pen_is_down)
        finally:C.CIRCLE_RADIUS=radius

    def test_deadline_lifts_pen_and_releases(self):
        self.p.set_origin()
        limit=C.RUN_LIMIT_SECONDS
        try:
            C.RUN_LIMIT_SECONDS=.02
            with self.assertRaises(RuntimeError):self.p.draw()
        finally:C.RUN_LIMIT_SECONDS=limit
        self.assertFalse(self.p.pen_is_down)
        self.assertFalse(self.p.referenced)
        self.assertTrue(all(pin.value()==0 for axis in (self.p.x,self.p.y) for pin in axis.pins))

    def test_keyboard_interrupt_during_motion(self):
        self.p.set_origin()
        old_step=P.Axis.step
        count=[0]
        def interrupted(axis,direction):
            old_step(axis,direction)
            count[0]+=1
            if count[0]==100:raise KeyboardInterrupt()
        P.Axis.step=interrupted
        try:
            with self.assertRaises(KeyboardInterrupt):self.p.draw()
        finally:P.Axis.step=old_step
        self.assertFalse(self.p.pen_is_down)
        self.assertFalse(self.p.referenced)

    def test_calibration_axis_and_distance(self):
        self.p.set_origin()
        self.p.calibration("x")
        self.assertEqual(self.p.position(),(60,10))
        self.p.calibration("y")
        self.assertEqual(self.p.position(),(10,60))
        self.assertFalse(self.p.pen_is_down)

    def test_phase_inversion_and_reverse(self):
        axis=P.Axis((1,2,3,4),-1)
        axis.step(1)
        self.assertEqual(axis.phase,7)
        axis.step(-1)
        self.assertEqual((axis.phase,axis.steps),(0,0))

    def test_servo_bounds(self):
        for value in (0,2500):
            with self.assertRaises(ValueError):self.p.pulse(value)


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    REPORT["tests_run"]=result.testsRun
    REPORT["all_passed"]=result.wasSuccessful()
    (ROOT/"验证"/"程序检查报告.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(REPORT,ensure_ascii=False,indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
