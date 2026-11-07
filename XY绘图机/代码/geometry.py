"""不依赖 ESP32 的几何与整数插补；也供电脑端验证使用。"""
import math


def circle(center, radius, segments=360):
    if radius <= 0 or segments < 16:
        raise ValueError("invalid circle")
    cx, cy = center
    points = [(cx + radius * math.cos(2 * math.pi * i / segments),
               cy + radius * math.sin(2 * math.pi * i / segments))
              for i in range(segments)]
    points.append(points[0])  # 使用同一坐标，避免浮点闭合尾差
    return points


def square(center, side):
    if side <= 0:
        raise ValueError("invalid square")
    cx, cy = center
    h = side / 2
    return [(cx-h, cy-h), (cx+h, cy-h), (cx+h, cy+h),
            (cx-h, cy+h), (cx-h, cy-h)]


def checked_targets(points, sx, sy, width, height):
    if sx <= 0 or sy <= 0:
        raise ValueError("steps/mm must be positive")
    result = []
    for x, y in points:
        if not (0 <= x <= width and 0 <= y <= height):
            raise ValueError("target outside work area: %s" % ((x, y),))
        result.append((round(x * sx), round(y * sy)))
    if not result:
        raise ValueError("empty path")
    return result


def dda(dx, dy):
    """每次最多让每个轴走一个半步；恰好到达正负整数目标。"""
    ax, ay = abs(dx), abs(dy)
    n = max(ax, ay)
    ex = ey = 0
    sign_x = 1 if dx > 0 else -1
    sign_y = 1 if dy > 0 else -1
    for _ in range(n):
        ex += ax
        ey += ay
        step_x = step_y = 0
        if ex >= n:
            ex -= n
            step_x = sign_x
        if ey >= n:
            ey -= n
            step_y = sign_y
        yield step_x, step_y
