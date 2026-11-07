"""Thonny 运行本文件，或与其余三个文件一起保存到板子根目录。"""
from plotter import Plotter

HELP = """
help                  commands
status                logical position and reference state
jog x 5 / jog y -5    pen-up jog; before zero each command <=5 mm
zero YES              declare CURRENT pen position the lower-left origin
up / down             lift / lower pen
servo 1200            test servo pulse (us); do this before attaching linkage
goto 10 10            pen-up absolute move within 0..90 mm
cal x / cal y         draw one 50 mm calibration line
dry                   full sequence with pen up
draw                  circle 80 mm + square 50 mm; then park and release
release               release coils; invalidates origin
quit                  pen up, release, leave the console
Ctrl-C                stop motion, lift pen and release; origin invalid
"""


def main():
    p = Plotter()
    print("XY plotter. No automatic homing, no automatic drawing.")
    print(HELP)
    while True:
        try:
            words = input("xy> ").strip().lower().split()
            if not words:
                continue
            cmd = words[0]
            if cmd == "help" and len(words) == 1:
                print(HELP)
            elif cmd == "status" and len(words) == 1:
                print("mm=", p.position(), "origin_valid=", p.referenced)
            elif cmd == "jog" and len(words) == 3:
                p.jog(words[1], float(words[2]))
            elif words == ["zero", "yes"]:
                p.set_origin()
                print("Current position is now (0,0); this did not find a limit.")
            elif words == ["up"]:
                p.pen_up()
            elif words == ["down"]:
                p.pen_down()
            elif cmd == "servo" and len(words) == 2:
                p.pulse(int(words[1]))
            elif cmd == "goto" and len(words) == 3:
                p.pen_up()
                p.move(float(words[1]), float(words[2]))
            elif cmd == "cal" and len(words) == 2:
                p.calibration(words[1])
            elif words == ["dry"]:
                p.draw(dry=True)
            elif words == ["draw"]:
                p.draw()
            elif words == ["release"]:
                p.pen_up()
                p.release()
            elif words == ["quit"]:
                p.emergency_stop()
                break
            else:
                print("Unknown command; type help.")
        except (KeyboardInterrupt, EOFError):
            p.emergency_stop()
            print("Stopped; origin invalid. Type quit to exit.")
        except Exception as error:
            p.emergency_stop()
            print("Stopped:", error, "-- origin invalid; check before zero YES.")


if __name__ == "__main__":
    main()
