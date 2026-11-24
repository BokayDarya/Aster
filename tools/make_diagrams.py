"""Векторные схемы проекта и отдельная UML-диаграмма физического формата А1."""
from pathlib import Path
import math
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
import pypdfium2 as pdf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/diagrams';OUT.mkdir(parents=True,exist_ok=True)
for name,file in [('T','times.ttf'),('TI','timesi.ttf'),('TB','timesbd.ttf')]:
    pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))

def label(c,x,y,lines,size=14,bold=False):
    if isinstance(lines,str):lines=lines.split('\n')
    for i,t in enumerate(lines):
        font='TB' if bold else 'T'
        if any('a'<=z.lower()<='z' for z in t):font='TI'
        c.setFont(font,size);c.drawCentredString(x,y+(len(lines)-1)*size*.55-i*size*1.1,t)

def box(c,x,y,w,h,text):
    c.rect(x,y,w,h);label(c,x+w/2,y+h/2-4,text)

def arrow(c,x,y,a,b,dashed=False):
    c.setDash(4,3) if dashed else c.setDash()
    c.line(x,y,a,b);c.setDash()
    angle=math.atan2(b-y,a-x)
    for d in [-.45,.45]:c.line(a,b,a-8*math.cos(angle+d),b-8*math.sin(angle+d))

def render(path,width=1800):
    d=pdf.PdfDocument(path);page=d[0];page.render(scale=width/page.get_width()).to_pil().save(path.with_suffix('.png'))

def architecture():
    p=OUT/'architecture.pdf';c=canvas.Canvas(str(p),pagesize=(170*mm,150*mm));c.setLineWidth(.8)
    box(c,100,355,280,60,'Браузер\nформа и графики')
    box(c,100,250,280,60,'Gateway\nHTTP → TCP-клиент')
    arrow(c,240,355,240,310);label(c,290,335,'HTTP')
    box(c,100,135,280,70,'Master\nпартии, полнота, VaR')
    arrow(c,240,250,240,205);label(c,295,228,'TCP')
    box(c,3,20,210,65,'Worker 1\nParallel.For + GBM')
    box(c,270,20,210,65,'Worker 2\nParallel.For + GBM')
    arrow(c,155,135,108,85);arrow(c,325,135,375,85)
    label(c,45,110,'TCP');label(c,430,110,'TCP')
    c.showPage();c.save();render(p)

def classes():
    p=OUT/'classes.pdf';c=canvas.Canvas(str(p),pagesize=(174*mm,120*mm));c.setLineWidth(.8);c.translate(2*mm,0)
    rows=[(260,'Gateway\nHTTP, экспорт','Wire\nкадр и вызов'),
          (180,'Master\nжизненный цикл','Worker\nпартия и потоки'),
          (100,'Store\nархив и сумма','Engine\nGBM и квантиль'),
          (20,'Simulation / Asset\nисходная модель','Validation\nграницы и Cholesky')]
    for y,a,b in rows:box(c,0,y,218,58,a);box(c,264,y,218,58,b)
    for y in [260,180,100]:arrow(c,109,y,109,y-22);arrow(c,373,y,373,y-22)
    arrow(c,218,289,264,289);arrow(c,218,209,264,209);arrow(c,264,129,218,49)
    c.showPage();c.save();render(p)

def lifecycle():
    p=OUT/'lifecycle.pdf';c=canvas.Canvas(str(p),pagesize=(174*mm,102*mm));c.setLineWidth(.8);c.translate(2*mm,1*mm)
    box(c,145,185,190,50,'running')
    xs=[25,185,345];texts=['completed','failed','cancelled']
    for x,t in zip(xs,texts):box(c,x,72,130,48,t);arrow(c,240,185,x+65,120)
    box(c,160,0,160,48,'interrupted');c.line(145,210,5,210);c.line(5,210,5,25);arrow(c,5,25,160,25)
    label(c,75,165,'Перезапуск')
    c.showPage();c.save();render(p)

def a1():
    p=OUT/'Бокая_Диаграмма_А1.pdf';W,H=841*mm,594*mm
    c=canvas.Canvas(str(p),pagesize=(W,H));c.setLineWidth(2)
    c.rect(20*mm,15*mm,W-30*mm,H-30*mm)
    label(c,W/2,H-45*mm,'Стресс-тестирование портфеля ценных бумаг с учётом прогноза',32,True)
    label(c,W/2,H-62*mm,'Диаграмма вариантов использования системы ASTER',28)
    c.rect(145*mm,65*mm,550*mm,445*mm)
    label(c,420*mm,490*mm,'ASTER: браузер, master, worker',26)
    def actor(x,y,text):
        c.circle(x,y+65,18);c.line(x,y+47,x,y-15);c.line(x-35,y+22,x+35,y+22);c.line(x,y-15,x-30,y-65);c.line(x,y-15,x+30,y-65);label(c,x,y-105,text,26)
    actor(85*mm,310*mm,'Пользователь');actor(750*mm,310*mm,'Администратор')
    def use(x,y,text):
        c.ellipse(x-92*mm,y-23*mm,x+92*mm,y+23*mm);label(c,x,y-5,text,26)
    user=[(270,445,'Изменить портфель\nи корреляции'),(270,360,'Задать прогноз\nи стресс'),(270,275,'Рассчитать риск'),(270,190,'Сравнить сценарии'),(270,105,'Экспортировать\nрезультаты')]
    admin=[(570,445,'Запустить систему'),(570,360,'Задать адреса узлов'),(570,275,'Просмотреть\nсостояние узлов'),(570,190,'Проверить модель'),(570,105,'Отменить расчёт')]
    for x,y,t in user+admin:use(x*mm,y*mm,t)
    c.line(85*mm,310*mm,120*mm,310*mm);c.line(715*mm,310*mm,750*mm,310*mm)
    for x,y,t in user:c.line(120*mm,310*mm,(x-92)*mm,y*mm)
    for x,y,t in admin[:3]:c.line(715*mm,310*mm,(x+92)*mm,y*mm)
    c.line(120*mm,310*mm,135*mm,310*mm);c.line(135*mm,310*mm,135*mm,75*mm)
    c.line(135*mm,75*mm,570*mm,75*mm);c.line(570*mm,75*mm,570*mm,82*mm)
    arrow(c,362*mm,275*mm,478*mm,190*mm,True);label(c,418*mm,262*mm,'«include»',24)
    label(c,W/2,53*mm,'Бокая Д. В. · ИТД-41 · Курсовой проект · 2026',26)
    label(c,W/2,33*mm,'А1 · 841 × 594 мм · Штамп кафедры не предоставлен',22)
    c.showPage();c.save();render(p,2400)

if __name__=='__main__':architecture();classes();lifecycle();a1()
