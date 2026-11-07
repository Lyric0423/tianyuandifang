#!/usr/bin/env python3
"""生成毫米制 Layer 0 切割图、编号排版、零件尺寸及两张示意图。

电脑依赖：ezdxf、numpy、matplotlib、shapely。不会修改老师的参考文件。
示意图是同一套参数生成的工程示意，不是加工或实物精度认证。
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/xy-plotter-matplotlib")
import csv
import json
import math
import random
from pathlib import Path
import ezdxf
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PatchPolygon, Circle, Rectangle, FancyArrowPatch
from matplotlib import font_manager
from shapely.geometry import Polygon, Point, box
from shapely.affinity import rotate, translate

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "图纸"
FIG = ROOT / "示意图"
SOURCE = ROOT.parent / "Gear+Bar.dxf"
BOARD = 195.0
GAP = 2.5
THICKNESS = 2.75             # 仅用于装配高度示意；槽宽不按板厚做过盈配合
SLIDE_SHIM = 0.30            # C1与两滑垫之间的固定胶带垫层；使C1高于B2
PIN_SLOT = 3.30
PEN_DIAMETER = 8.0          # 请先实测笔身；笔芯可套胶带增粗至这个直径
PEN_GUIDE = PEN_DIAMETER + 0.40
PITCH = 4.0
TEETH = 16
PITCH_RADIUS = TEETH * PITCH / (2 * math.pi)
ADDENDUM = PITCH / math.pi
GEAR_TIP_GAP = PITCH_RADIUS - ADDENDUM + 0.10  # 含0.10mm初始径向啮合余量
TOOTH_DEPTH = 27.72742506569344 - 25.155945976223535
RAMP = 0.879497646739595
TIP_FLAT = 1.115750634687685
BLUE = "#2265ad"
TEAL = "#008777"
ORANGE = "#d77b20"
INK = "#182d45"


def circle_hole(x, y, diameter):
    return {"type": "circle", "x": x, "y": y, "diameter": diameter}


def slot_hole(x0, y0, x1, y1, width):
    return {"type": "slot", "start": [x0, y0], "end": [x1, y1], "width": width}


def d_hole(x, y, diameter=4.8, flats=2.8):
    return {"type": "double_D", "x": x, "y": y,
            "diameter": diameter, "flats": flats}


def rect_points(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def rack_points(length, height):
    """保留参考齿条的节距、齿顶宽和斜边；只缩短齿条并加宽背板。"""
    root = height - TOOTH_DEPTH
    profile = [(0, root)]
    x = 0.0
    while x + PITCH <= length + 1e-8:
        profile.extend([(x+RAMP, height), (x+RAMP+TIP_FLAT, height),
                        (x+2*RAMP+TIP_FLAT, root), (x+PITCH, root)])
        x += PITCH
    if x < length:
        raise ValueError("rack length must be a multiple of 4 mm")
    return [(0, 0), (length, 0)] + list(reversed(profile))


def ring(hole):
    if hole["type"] == "circle":
        return list(Point(hole["x"], hole["y"]).buffer(hole["diameter"]/2, resolution=32).exterior.coords)
    if hole["type"] == "slot":
        from shapely.geometry import LineString
        return list(LineString([hole["start"], hole["end"]]).buffer(hole["width"]/2, resolution=24).exterior.coords)
    x, y = hole["x"], hole["y"]
    r, f = hole["diameter"]/2, hole["flats"]/2
    a = math.asin(f/r)
    angles = list(np.linspace(-a, a, 32)) + list(np.linspace(math.pi-a, math.pi+a, 32))
    return [(x+r*math.cos(t), y+r*math.sin(t)) for t in angles]


def part(pid, name, w, h, holes=None, outer=None, note=""):
    outline=list(outer or rect_points(w,h))
    if math.dist(outline[0],outline[-1]) < 1e-8:
        outline.pop()
    return {"id": pid, "name": name, "width": w, "height": h,
            "outer": outline, "holes": holes or [], "note": note}


def make_parts():
    parts = []
    parts.append(part("A1", "Y左齿条导轨", 160, 24,
        [slot_hole(18,10,142,10,PIN_SLOT), circle_hole(6,10,3.3), circle_hole(154,10,3.3)],
        rack_points(160,24), "安装时旋转90°，齿朝左；导槽位于全局x=14"))
    parts.append(part("A2", "Y右导轨",160,16,
        [slot_hole(18,8,142,8,PIN_SLOT), circle_hole(6,8,3.3),circle_hole(154,8,3.3)]))
    for pid in ("A3","A4"):
        parts.append(part(pid,"前后横向连接条",156,12,
            [circle_hole(14,6,3.3),circle_hole(144,6,3.3)]))
    bridge_holes = [slot_hole(24,16,136,16,PIN_SLOT)]
    bridge_holes += [circle_hole(x,y,3.3) for x in (14,144) for y in (7,25)]
    parts.append(part("B1","X齿条横梁",156,32,bridge_holes,rack_points(156,32),
        "X导槽兼横梁；四个端部孔装Y滑动销；左侧导销同时穿过B2"))
    body_x = 38-GEAR_TIP_GAP-8
    parts.append(part("B2","Y电机侧挂板",56,48,
        [circle_hole(38-GEAR_TIP_GAP,24,12),
         slot_hole(body_x-2,6.5,body_x+2,6.5,4.2),
         slot_hole(body_x-2,41.5,body_x+2,41.5,4.2),
         circle_hole(52,15,3.3),circle_hole(52,33,3.3)],
        note="装到B1上表面：左下角位于横梁局部(-38,-8)，两孔与B1左侧导销孔共用；结合面少量胶固定"))
    shaft_y = 32 + GEAR_TIP_GAP
    holes = [circle_hole(x,40,3.3) for x in (13,33)]
    holes += [circle_hole(23,10,PEN_GUIDE), circle_hole(14,10,3.3),circle_hole(32,10,3.3)]
    holes += [slot_hole(x,17,x,23,3.2) for x in (8,42)]
    holes += [circle_hole(23,shaft_y+24,12)]
    holes += [slot_hole(x,shaft_y+24+8-2,x,shaft_y+24+8+2,4.2) for x in (5.5,40.5)]
    carrier_shape=box(0,0,46,88)
    for x0,x1 in ((-1,8),(38,47)):
        for y in (31,49):
            carrier_shape=carrier_shape.difference(box(x0,y-4,x1,y+4))
    parts.append(part("C1","X滑动笔架",46,88,holes,list(carrier_shape.exterior.coords),
        "长边沿Y；四个侧缺口避让Y导销头。导销孔(13,40)/(33,40)，笔孔(23,10)"))
    for pid in ("C2","C3"):
        parts.append(part(pid,"X滑动垫片",10,12,[circle_hole(5,6,3.3)],
            note="各一片固定于C1底部两个导销孔处；固定结合面再垫约0.30mm胶带，使笔架高于B2"))
    parts.append(part("D1","上层笔导向环",28,20,
        [circle_hole(14,10,PEN_GUIDE),circle_hole(5,10,3.3),circle_hole(23,10,3.3)],
        note="M3立柱固定在C1笔孔两侧；上下导向孔保持同轴，间隔约20mm"))
    for pid in ("D2","D3"):
        parts.append(part(pid,"笔身限位/抬笔环",20,16,
            [circle_hole(10,8,PEN_DIAMETER+0.2)],note="套在笔上，用胶带形成止挡；D2供舵盘从下方托起"))
    for i in range(4):
        parts.append(part("E%d"%(i+1),"底脚垫",24,20,[circle_hole(12,10,3.3)]))
    source = ezdxf.readfile(SOURCE)
    gear = next(iter(source.modelspace().query("LWPOLYLINE")))
    raw = [(float(p[0]),float(p[1])) for p in gear.get_points()]
    xmin,ymin = min(x for x,y in raw),min(y for x,y in raw)
    xmax,ymax = max(x for x,y in raw),max(y for x,y in raw)
    for pid in ("G1","G2"):
        parts.append(part(pid,"参考原轮廓16齿齿轮",xmax-xmin,ymax-ymin,
            [d_hole(-xmin,-ymin)],[(x-xmin,y-ymin) for x,y in raw],
            "外形与老师参考文件相同；双扁孔4.8×2.8，先试切验证实轴"))
    holes = [slot_hole(5,y,13,y,w) for y,w in zip((5,12,19),(3.1,3.3,3.5))]
    holes += [d_hole(25,y,d,f) for y,d,f in ((5,4.8,2.8),(12,4.9,2.9),(19,5.0,3.0))]
    parts.append(part("Q1","孔槽试切片",32,24,holes,note="左：槽宽3.1/3.3/3.5；右：双扁孔4.8×2.8/4.9×2.9/5.0×3.0（由下到上）"))
    return parts


def contains(a,b):
    return a[0]<=b[0]+1e-8 and a[1]<=b[1]+1e-8 and a[0]+a[2]>=b[0]+b[2]-1e-8 and a[1]+a[3]>=b[1]+b[3]-1e-8


def try_pack(parts, order):
    free = [(1.5,1.5,BOARD-3+GAP,BOARD-3+GAP)]
    placed = {}
    for index in order:
        p = parts[index]
        choices=[]
        for r in free:
            for turn in (False,True):
                w,h = (p["height"],p["width"]) if turn else (p["width"],p["height"])
                aw,ah=w+GAP,h+GAP
                if aw<=r[2]+1e-8 and ah<=r[3]+1e-8:
                    choices.append(((min(r[2]-aw,r[3]-ah),max(r[2]-aw,r[3]-ah)),r,turn,w,h))
        if not choices:
            return None
        _,r,turn,w,h=min(choices,key=lambda c:c[0])
        used=(r[0],r[1],w+GAP,h+GAP)
        placed[p["id"]]={"x":r[0],"y":r[1],"rotated":turn,"width":w,"height":h}
        next_free=[]
        ux,uy,uw,uh=used
        for fx,fy,fw,fh in free:
            if ux>=fx+fw-1e-8 or ux+uw<=fx+1e-8 or uy>=fy+fh-1e-8 or uy+uh<=fy+1e-8:
                next_free.append((fx,fy,fw,fh));continue
            if ux>fx:next_free.append((fx,fy,ux-fx,fh))
            if ux+uw<fx+fw:next_free.append((ux+uw,fy,fx+fw-ux-uw,fh))
            if uy>fy:next_free.append((fx,fy,fw,uy-fy))
            if uy+uh<fy+fh:next_free.append((fx,uy+uh,fw,fy+fh-uy-uh))
        free=[]
        for a in sorted(set(next_free),key=lambda r:r[2]*r[3],reverse=True):
            if a[2]>1e-6 and a[3]>1e-6 and not any(contains(b,a) for b in free):
                free.append(a)
    return placed


def pack(parts):
    orders = [sorted(range(len(parts)),key=lambda i:parts[i]["width"]*parts[i]["height"],reverse=True),
              sorted(range(len(parts)),key=lambda i:max(parts[i]["width"],parts[i]["height"]),reverse=True)]
    rng=random.Random(20261107)
    for _ in range(5000):
        if orders:
            order=orders.pop(0)
        else:
            order=list(range(len(parts)))
            rng.shuffle(order)
        placement=try_pack(parts,order)
        if placement:
            return placement
    raise RuntimeError("195x195 排版未成功；不能输出超出板材的提交文件")


def transform(x,y,p,placement):
    if placement["rotated"]:
        x,y=p["height"]-y,x
    return x+placement["x"],y+placement["y"]


def new_dxf():
    doc=ezdxf.new("R2010")
    doc.units=4
    doc.header["$MEASUREMENT"]=1
    if "Defpoints" in doc.layers:
        doc.layers.remove("Defpoints")
    return doc


def add_part_dxf(msp,p,placement):
    tx=lambda pt:transform(pt[0],pt[1],p,placement)
    msp.add_lwpolyline([tx(pt) for pt in p["outer"]],close=True,dxfattribs={"layer":"0"})
    for hole in p["holes"]:
        kind=hole["type"]
        if kind=="circle":
            msp.add_circle(tx((hole["x"],hole["y"])),hole["diameter"]/2,dxfattribs={"layer":"0"})
        elif kind=="slot":
            a=np.array(hole["start"],dtype=float);b=np.array(hole["end"],dtype=float)
            direction=(b-a)/np.linalg.norm(b-a)
            normal=np.array([-direction[1],direction[0]])*hole["width"]/2
            points=[a-normal,b-normal,b+normal,a+normal]
            msp.add_lwpolyline([(*tx(v),bulge) for v,bulge in zip(points,(0,1,0,1))],
                               format="xyb",close=True,dxfattribs={"layer":"0"})
        else:
            # 双扁孔用精确圆弧和直线，不能用圆孔替代。
            cx,cy=hole["x"],hole["y"]
            r,f=hole["diameter"]/2,hole["flats"]/2
            a=math.degrees(math.asin(f/r))
            offset=90 if placement["rotated"] else 0
            center=tx((cx,cy))
            msp.add_arc(center,r,-a+offset,a+offset,dxfattribs={"layer":"0"})
            msp.add_arc(center,r,180-a+offset,180+a+offset,dxfattribs={"layer":"0"})
            x=math.sqrt(r*r-f*f)
            for sign in (-1,1):
                msp.add_line(tx((cx-x,cy+sign*f)),tx((cx+x,cy+sign*f)),dxfattribs={"layer":"0"})


def draw_part(ax,p,tx=lambda p:p,face="#e7f0fa",edge=BLUE,alpha=1,lw=.7):
    ax.add_patch(PatchPolygon([tx(v) for v in p["outer"]],closed=True,
        facecolor=face,edgecolor=edge,lw=lw,alpha=alpha))
    for hole in p["holes"]:
        ax.add_patch(PatchPolygon([tx(v) for v in ring(hole)],closed=True,
            facecolor="white",edgecolor=edge,lw=lw,alpha=alpha))


def set_fonts():
    path="/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    if Path(path).exists():
        font_manager.fontManager.addfont(path)
        plt.rcParams["font.family"]="Arial Unicode MS"
    else:
        plt.rcParams["font.family"]=["Noto Sans CJK SC","DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"]=False
    plt.rcParams["svg.fonttype"]="path"  # 分享SVG时中文不依赖接收方字体


def save_pair(fig,path,dpi=190):
    fig.savefig(path.with_suffix(".png"),dpi=dpi,facecolor="white",bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"),facecolor="white",bbox_inches="tight")
    plt.close(fig)


def packing_diagram(parts,placement):
    fig,ax=plt.subplots(figsize=(10,10))
    ax.add_patch(Rectangle((0,0),BOARD,BOARD,fill=False,ec=INK,lw=1))
    for p in parts:
        loc=placement[p["id"]]
        draw_part(ax,p,lambda v:transform(*v,p,loc))
        x,y=transform(2,2,p,loc)
        ax.text(x,y,p["id"],fontsize=8,color=INK,ha="left",va="bottom",
                bbox={"fc":"white","ec":"none","alpha":.85,"pad":.7})
    ax.set(xlim=(-4,199),ylim=(-4,199),aspect="equal",xlabel="mm",ylabel="mm")
    ax.set_title("195 × 195 mm 编号排版｜仅对应主切割 DXF\n编号、外框和坐标轴均不进入激光切割文件",fontsize=14,pad=16)
    fig.tight_layout()
    save_pair(fig,OUT/"02_编号排版")


def dimension_catalog(parts):
    cols=4;rows=math.ceil(len(parts)/cols)
    fig,axes=plt.subplots(rows,cols,figsize=(16,rows*3.4))
    for ax,p in zip(axes.flat,parts):
        draw_part(ax,p)
        w,h=p["width"],p["height"]
        pad=max(w,h)*.13+2
        ax.set(xlim=(-pad,w+pad),ylim=(-pad,h+pad),aspect="equal")
        ax.set_title("%s  %s\n外包尺寸 %.2f × %.2f mm"%(p["id"],p["name"],w,h),fontsize=10)
        ax.tick_params(labelsize=7)
        for i,hole in enumerate(p["holes"],1):
            if hole["type"]=="slot":x,y=hole["start"]
            else:x,y=hole["x"],hole["y"]
            ax.text(x,y,str(i),fontsize=7,color=ORANGE,ha="center",va="center")
    for ax in list(axes.flat)[len(parts):]:ax.axis("off")
    fig.suptitle("零件尺寸与孔位索引｜单位 mm｜孔号详细坐标见 零件孔位.csv\n每个小图自动缩放，不可拿屏幕长度直接量尺寸",fontsize=16,y=1.01)
    fig.tight_layout(pad=2)
    fig.savefig(OUT/"03_零件尺寸图.svg",bbox_inches="tight",facecolor="white")
    plt.close(fig)


def label(ax,text,xy,xytext,color=INK):
    ax.annotate(text,xy=xy,xytext=xytext,fontsize=10,color=color,
        arrowprops={"arrowstyle":"-","color":color,"lw":1},
        bbox={"boxstyle":"round,pad=.35","fc":"white","ec":"#d6e0eb","alpha":.96})


def assembly_diagram(parts):
    byid={p["id"]:p for p in parts}
    fig=plt.figure(figsize=(16,10))
    gs=fig.add_gridspec(2,2,width_ratios=(1.55,1),height_ratios=(1,1))
    ax=fig.add_subplot(gs[:,0]); side=fig.add_subplot(gs[0,1]); info=fig.add_subplot(gs[1,1])
    ax.add_patch(Rectangle((-5,-7),170,180,fc="#faf9f5",ec="#cbc9c1",lw=.7))
    ax.add_patch(Circle((80,51),40,fill=False,ec="#b6bcc5",lw=1.4))
    ax.add_patch(Rectangle((55,26),50,50,fill=False,ec="#b6bcc5",lw=1.4))
    for pid,y in (("A3",0),("A4",148)):
        draw_part(ax,byid[pid],lambda v,y=y:(v[0],v[1]+y),face="#ccd8e3",edge="#71869b")
    draw_part(ax,byid["A1"],lambda v:(24-v[1],v[0]),face="#d5e5f4")
    draw_part(ax,byid["A2"],lambda v:(136+v[1],v[0]),face="#d5e5f4")
    for x in (14,144):
        for y in (6,154):ax.add_patch(Circle((x,y),2.2,fc=INK,ec="white",lw=.6))
    oy=65;cx=80
    draw_part(ax,byid["B1"],lambda v:(v[0],v[1]+oy),face="#b7d6ed",alpha=.9)
    draw_part(ax,byid["B2"],lambda v:(v[0]-38,v[1]+oy-8),face="#d6e6f3",alpha=.9)
    for px,pid in ((cx-10,"C2"),(cx+10,"C3")):
        draw_part(ax,byid[pid],lambda v,px=px:(v[0]+px-5,v[1]+oy+10),face="#91c8b8",edge=TEAL)
    # 展示运动状态(45,45)，原点对应滑块中心x=35、横梁下边y=20。
    draw_part(ax,byid["C1"],lambda v:(v[0]+cx-23,v[1]+oy-24),face="#c8e6de",edge=TEAL,alpha=.8)
    def gear_at(gx,gy,pid):
        p=byid[pid]
        angle=math.radians(98 if pid=="G1" else 8)
        def tx(v):
            x,y=v[0]-p["width"]/2,v[1]-p["height"]/2
            return (gx+x*math.cos(angle)-y*math.sin(angle),gy+x*math.sin(angle)+y*math.cos(angle))
        draw_part(ax,p,tx,face="#f5d7af",edge=ORANGE)
    gear_at(-GEAR_TIP_GAP,oy+16,"G1")
    gear_at(cx,oy+32+GEAR_TIP_GAP,"G2")
    for x,y in ((-GEAR_TIP_GAP-8,oy+16),(cx,oy+32+GEAR_TIP_GAP+8)):
        ax.add_patch(Circle((x,y),14,fc="#9bb9d5",ec=BLUE,lw=1,alpha=.75))
        ax.text(x,y,"步进",fontsize=8,color=INK,ha="center",va="center")
    ax.add_patch(Rectangle((cx+9,oy-10),23,23,fc="#8bb9df",ec=BLUE,alpha=.9))
    ax.text(cx+20.5,oy+1.5,"SG90",fontsize=8,color=INK,ha="center",va="center")
    ax.add_patch(Circle((cx,oy-14),4.2,fc=INK,ec="white",lw=1))
    ax.annotate("X",xy=(122,oy+16),xytext=(90,oy+16),color=TEAL,
        arrowprops={"arrowstyle":"->","color":TEAL,"lw":2},fontsize=12)
    ax.annotate("Y",xy=(145,128),xytext=(145,105),color=BLUE,
        arrowprops={"arrowstyle":"->","color":BLUE,"lw":2},fontsize=12)
    label(ax,"A1：齿条＋长槽导轨",(10,124),(-44,144))
    label(ax,"B2：侧挂 Y 电机\n齿轮位于导轨同层",(-12,82),(-49,38))
    label(ax,"B1：带齿横梁\n由两根 Y 导轨支撑",(128,94),(165,142))
    label(ax,"C1：滑动笔架\n两个 M3 导销防转",(83,81),(166,103))
    label(ax,"笔尖：位于横梁前方\n普通纸固定在桌面",(80,51),(165,55))
    ax.plot(35,6,"+",color=ORANGE,ms=10)
    ax.text(39,3,"软件原点 (0,0)",fontsize=9,color=ORANGE)
    ax.set(xlim=(-53,231),ylim=(-15,178),aspect="equal")
    ax.set_anchor("N")
    ax.axis("off");ax.set_title("俯视装配关系｜绘图范围 90 × 90 mm",loc="left",fontsize=14,pad=16,color=INK)
    # 独立高度示意：水平位置为示意排布；标签错开并用引线标高。
    side.axhline(0,color=INK,lw=1)
    z_bridge=30+THICKNESS
    z_shoe=30+2*THICKNESS
    z_carriage=30+3*THICKNESS+SLIDE_SHIM
    levels=[(0,THICKNESS,9,24,"E 底脚"),(30-THICKNESS,THICKNESS,8,80,"A3/A4 横条"),
            (30,THICKNESS,13,75,"A1/A2 导轨"),(z_bridge,THICKNESS,19,88,"B1 横梁"),
            (z_shoe,THICKNESS,48,12,"C2/C3 滑垫"),(z_carriage,THICKNESS,48,48,"C1 笔架")]
    for index,(z,h,x,w,name) in enumerate(levels):
        side.add_patch(Rectangle((x,z),w,h,fc="#d6e6f3",ec=BLUE,lw=.7))
        label_y=2 if index==0 else 18+index*6
        side.annotate(name+"  z=%.2f"%z,xy=(x+w,z+h/2),xytext=(103,label_y),
            fontsize=8,va="center",color=INK,arrowprops={"arrowstyle":"-","color":"#71869b","lw":.6})
    side.plot([20,20],[3,32],color="#7a8795",lw=2)
    side.plot([58,58],[z_carriage+THICKNESS,59],color="#7a8795",lw=1.5)
    side.add_patch(Rectangle((48,59),28,2.75,fc="#c8e6de",ec=TEAL,lw=.8))
    side.text(103,61,"D1 上导向环  z≈59",fontsize=8,va="center",color=INK)
    side.add_patch(Rectangle((69,z_carriage+THICKNESS),28,19,fc="#9bb9d5",ec=BLUE,lw=.8))
    side.plot([62,62],[0,75],color=INK,lw=3)
    side.add_patch(Rectangle((54,47),16,2.75,fc="#f5d7af",ec=ORANGE))
    side.annotate("抬笔约 3 mm",xy=(62,51),xytext=(4,73),fontsize=10,color=TEAL,
        arrowprops={"arrowstyle":"->","color":TEAL})
    side.text(4,6,"M3×40＋螺母调平",fontsize=8,color=INK)
    side.set(xlim=(0,178),ylim=(-3,81));side.axis("off")
    side.set_title("侧视层次｜单位 mm，轴向高度可微调",loc="left",fontsize=13,color=INK,pad=15)
    info.axis("off")
    info.text(0,1,"装配要点",fontsize=16,color=INK,va="top",weight="bold")
    info.text(0,.87,"① 长槽内的 M3 销能滑动，不能夹紧导轨。\n\n"
        "② 螺母成对锁紧，留约 0.15–0.25 mm 轴向间隙。\n\n"
        "③ 滑垫结合面垫约 0.3 mm 胶带；侧缺口避让销头。\n\n"
        "④ SG90 侧卧，输出轴水平；舵盘从下方托起 D2。\n\n"
        "⑤ 两导向孔同轴，笔能上下滑；橡皮筋轻压落笔。\n\n"
        "⑥ M3 导销、螺母和电线均需检查运动干涉。",
        fontsize=11,color=INK,va="top",linespacing=1.5)
    info.text(0,.02,"示意不代替实物试装：电机轴偏心、板厚、切缝先核对。",fontsize=9,color=ORANGE)
    fig.suptitle("XY 绘图机｜示意图 1：机械结构与装配",fontsize=22,color=INK,y=1.01)
    fig.subplots_adjust(wspace=.10,hspace=.25)
    save_pair(fig,FIG/"01_机械结构示意图")


def wiring_diagram():
    fig,ax=plt.subplots(figsize=(15,10))
    ax.set(xlim=(0,150),ylim=(0,100));ax.axis("off")
    ax.text(4,96,"XY 绘图机｜示意图 2：接线与运行顺序",fontsize=22,color=INK,va="top")
    def panel(x,y,w,h,title,color):
        ax.add_patch(Rectangle((x,y),w,h,fc="#f4f8fc",ec=color,lw=1.3))
        ax.text(x+2,y+h-3,title,fontsize=12,color=color,va="top")
    panel(6,35,35,49,"经典 ESP32",BLUE)
    panel(65,65,36,19,"ULN2003 · X",TEAL)
    panel(65,39,36,19,"ULN2003 · Y",ORANGE)
    panel(116,65,28,19,"28BYJ-48 · X",TEAL)
    panel(116,39,28,19,"28BYJ-48 · Y",ORANGE)
    panel(65,15,36,17,"SG90 抬笔",BLUE)
    xys=[(74,(16,17,18,19),TEAL),(48,(21,22,23,25),ORANGE)]
    for base,pins,color in xys:
        for i,pin in enumerate(pins):
            yy=base+3-i*3
            source_y=(74-i*3) if base==74 else (56-i*3)
            ax.text(10,source_y,"GPIO %d"%pin,fontsize=10,color=color,va="center")
            ax.plot([41,52+i*2,52+i*2,65],[source_y,source_y,yy,yy],color=color,lw=1)
            ax.text(68,yy,"IN%d"%(i+1),fontsize=9,color=color,va="center")
        ax.annotate("五线插头",xy=(116,base),xytext=(102,base),fontsize=8,color=color,
            arrowprops={"arrowstyle":"->","color":color})
    ax.text(10,40,"GPIO 26",fontsize=10,color=BLUE,va="center")
    ax.plot([41,48,48,65],[40,40,23,23],color=BLUE,lw=1.4)
    ax.text(68,23,"信号：橙 / 黄",fontsize=10,color=BLUE,va="center")
    ax.text(108,23,"输出轴水平放置\n舵盘托起笔环",fontsize=10,color=INK,va="center")
    # 电源信息独立排成两个总线框，避免长电源线与信号线交叉造成误读。
    panel(6,6,35,23,"供电",INK)
    ax.text(8,21,"ESP32：电脑 USB\n电机与舵机：外接稳定 5V",fontsize=9,color=INK,va="top",linespacing=1.8)
    ax.text(47,7,"外接 +5V → 两块 ULN2003 的 + / VCC；SG90 红线\n"
        "外接 GND → 两块 ULN2003 的 − / GND；SG90 棕/黑线；ESP32 GND",
        fontsize=10,color=INK,va="bottom",linespacing=1.8)
    ax.text(6,89,"驱动板电源按实际丝印确认；GPIO 仅送控制信号，所有模块必须共地。",fontsize=11,color=INK)
    ax.text(6,32,"先拆下旧 OLED / 雷达接线，避免 GPIO18/19/23/26 重复占用。",fontsize=10,color=ORANGE)
    fig.text(.52,.025,"运行：检查方向 → 设置原点 → cal x / cal y 标定 → dry 空走 → 重新设原点 → draw",ha="center",fontsize=12,color=INK)
    save_pair(fig,FIG/"02_接线与运行示意图")


def validate(parts,placement):
    from ezdxf import bbox
    report={"units":"mm","board_mm":[195,195],"part_count":len(parts),"minimum_part_gap_mm":999,
            "warnings":["未进行实物试装或电机带载验证；孔槽配合、舵机托笔位置需试切与调试。"]}
    geometries=[]
    for p in parts:
        outer=Polygon(p["outer"])
        assert outer.is_valid,(p["id"],"invalid outer")
        for hole in p["holes"]:
            inner=Polygon(ring(hole))
            assert inner.is_valid,(p["id"],"invalid hole")
            assert outer.contains(inner),(p["id"],"hole outside")
        rings=[Polygon(ring(h)) for h in p["holes"]]
        for i,h in enumerate(rings):
            assert all(not h.intersects(o) for o in rings[i+1:]),(p["id"],"overlapping holes")
        loc=placement[p["id"]]
        g=Polygon([transform(*pt,p,loc) for pt in p["outer"]])
        assert box(0,0,BOARD,BOARD).contains(g),(p["id"],"outside board")
        for other in geometries:
            distance=g.distance(other)
            report["minimum_part_gap_mm"]=min(report["minimum_part_gap_mm"],distance)
            assert distance>=2.0-1e-6,(p["id"],"parts too close",distance)
        geometries.append(g)
    doc=ezdxf.readfile(OUT/"01_提交切割_195x195_Layer0.dxf")
    # ezdxf 读入时会自动补建 Defpoints；检查磁盘原始 LAYER 表而非内存默认值。
    raw=(OUT/"01_提交切割_195x195_Layer0.dxf").read_text(encoding="utf-8").splitlines()
    tags=[(int(raw[i].strip()),raw[i+1].strip()) for i in range(0,len(raw),2)]
    layer_names=[]
    for i,tag in enumerate(tags):
        if tag==(0,"LAYER"):
            for code,value in tags[i+1:]:
                if code==0:break
                if code==2:layer_names.append(value);break
    assert layer_names==["0"],layer_names
    assert all(e.dxf.layer=="0" for e in doc.modelspace())
    assert not list(doc.modelspace().query("TEXT MTEXT DIMENSION INSERT"))
    assert not doc.audit().has_errors
    # 检查所有独立线/圆弧的端点成对闭合，所有多段线自身闭合且无零长度边。
    from collections import Counter
    endpoints=Counter()
    def endpoint_key(v):return (round(v[0],6),round(v[1],6))
    for entity in doc.modelspace():
        kind=entity.dxftype()
        if kind=="LWPOLYLINE":
            assert entity.closed
            vertices=[(v[0],v[1]) for v in entity.get_points()]
            assert all(math.dist(a,b)>1e-8 for a,b in zip(vertices,vertices[1:]+vertices[:1]))
        elif kind=="LINE":
            endpoints[endpoint_key(entity.dxf.start)]+=1
            endpoints[endpoint_key(entity.dxf.end)]+=1
        elif kind=="ARC":
            endpoints[endpoint_key(entity.start_point)]+=1
            endpoints[endpoint_key(entity.end_point)]+=1
        else:assert kind=="CIRCLE"
    assert all(degree==2 for degree in endpoints.values()),"open or branched cut contour"
    # 对滑销、笔架缺口和B2/滑垫间的关键平面净空做全行程抽查。
    lookup={p["id"]:p for p in parts}
    for cx in np.linspace(35,125,91):
        carrier=translate(Polygon(lookup["C1"]["outer"]),cx-23,-24)
        for hx in (14,144):
            for hy in (7,25):
                assert carrier.intersection(Point(hx,hy).buffer(3)).area<1e-7,"Y screw head collision"
        for pinx in (cx-10,cx+10):
            assert 24<=pinx<=136
            assert pinx-5>=18+2-1e-8,"shoe/B2 side clearance"
    # 原参考齿轮与复用齿条齿形，在一个齿距内滚动的理想二维几何抽查。
    gear=lookup["G1"]
    profile=translate(Polygon(gear["outer"]),-gear["width"]/2,-gear["height"]/2)
    rack=Polygon(rack_points(80,24))
    max_mesh_overlap=0
    for distance in np.linspace(0,4,49):
        current=translate(rotate(profile,8-distance/PITCH_RADIUS*180/math.pi,origin=(0,0)),
                          40+distance,24+GEAR_TIP_GAP)
        max_mesh_overlap=max(max_mesh_overlap,current.intersection(rack).area)
    assert max_mesh_overlap<1e-5,"rack/pinion tooth interference"
    b=bbox.extents(doc.modelspace())
    report["cut_bounds_mm"]=[list(b.extmin)[:2],list(b.extmax)[:2]]
    report["all_cut_contours_closed"]=True
    report["layer_names"]=["0"]
    report["rack_pitch_mm"]=PITCH
    report["pinion_teeth"]=TEETH
    report["nominal_mm_per_revolution"]=PITCH*TEETH
    report["slot_pin_mechanical_travel_mm"]={"X":112-20,"Y":124-18}
    report["configured_work_travel_mm"]=[90,90]
    report["nominal_assembly_height_mm"]={"rail_bottom":30,"bridge_bottom":30+THICKNESS,
        "carriage_bottom":30+3*THICKNESS+SLIDE_SHIM,"upper_pen_guide_bottom":59}
    report["carriage_over_motor_bracket_clearance_mm"]=SLIDE_SHIM
    report["critical_clearance_sampling"]="X 91 positions; Y screw-head envelope diameter 6mm"
    report["ideal_mesh_max_overlap_mm2"]=max_mesh_overlap
    (OUT/"图纸检查报告.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def main():
    OUT.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True)
    set_fonts()
    parts=make_parts();placement=pack(parts)
    doc=new_dxf()
    for p in parts:add_part_dxf(doc.modelspace(),p,placement[p["id"]])
    doc.saveas(OUT/"01_提交切割_195x195_Layer0.dxf")
    coupon=next(p for p in parts if p["id"]=="Q1")
    doc=new_dxf();add_part_dxf(doc.modelspace(),coupon,{"x":0,"y":0,"rotated":False})
    doc.saveas(OUT/"04_单独试切_Q1_不要重复排版.dxf")
    (OUT/"参数与零件.json").write_text(json.dumps({"board_mm":BOARD,"thickness_assumption_mm":THICKNESS,
        "fixed_shim_between_carriage_and_shoes_mm":SLIDE_SHIM,
        "nominal_guide_slot_mm":PIN_SLOT,"pen_body_diameter_mm":PEN_DIAMETER,
        "gear_pitch_radius_mm":PITCH_RADIUS,"gear_center_outside_tooth_tip_mm":GEAR_TIP_GAP,
        "parts":parts,"placement":placement},ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"零件孔位.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f);writer.writerow(["编号","名称","外包长mm","外包宽mm","孔号","孔类型","局部坐标与尺寸mm","装配备注"])
        for p in parts:
            for i,h in enumerate(p["holes"],1):
                writer.writerow([p["id"],p["name"],p["width"],p["height"],i,h["type"],json.dumps(h,ensure_ascii=False),p["note"]])
    packing_diagram(parts,placement)
    dimension_catalog(parts)
    assembly_diagram(parts)
    wiring_diagram()
    report=validate(parts,placement)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
