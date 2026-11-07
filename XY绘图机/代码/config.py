"""经典 ESP32 + 两套 5V 28BYJ-48/ULN2003 + SG90。尺寸单位 mm。"""

# 按驱动板 IN1、IN2、IN3、IN4 顺序接线；不是直接连接电机绕组。
X_PINS = (16, 17, 18, 19)
Y_PINS = (21, 22, 23, 25)
SERVO_PIN = 26
X_DIRECTION = 1              # jog x 5 应让笔向右；相反时改为 -1
Y_DIRECTION = 1              # jog y 5 应让笔远离自己；相反时改为 -1

# 老师提供的齿轮：16 齿，齿条节距 4 mm，即每转推进 64 mm。
# 4096 是半步数的初值，减速比、切割和装配误差应通过 50 mm 测试标定。
X_STEPS_PER_MM = 4096.0 / 64.0
Y_STEPS_PER_MM = 4096.0 / 64.0
WORK_X = 90.0
WORK_Y = 90.0
CENTER = (45.0, 45.0)
CIRCLE_RADIUS = 40.0
SQUARE_SIDE = 50.0
CIRCLE_SEGMENTS = 360

DRAW_FEED = 2.0              # mm/s，约 4 分钟完成一组图形
TRAVEL_FEED = 3.5
JOG_FEED = 1.5
MIN_FEED = 0.5
ACCELERATION = 8.0           # mm/s²，每条边停稳，圆弧整体连续加减速
MAX_HALFSTEPS_PER_SECOND = 350
MAX_UNREFERENCED_JOG = 5.0   # 未设原点时，一次只能点动 5 mm
RUN_LIMIT_SECONDS = 570     # 软件运行预算；不是断电保护或硬件限位

# 先拆开舵盘连杆或托住笔测试。实际抬笔方向与安装方向有关。
# 可先用 servo 1200 / servo 1600 调整；确认抬起约 3 mm、落笔不顶死。
SERVO_UP_US = 1200
SERVO_DOWN_US = 1600
SERVO_MIN_US = 800
SERVO_MAX_US = 2200
SERVO_SETTLE_MS = 350
