"""Собирает отдельное руководство. Пояснительную записку не открывает."""
from pathlib import Path
import hashlib
import json
import re
from datetime import datetime, timezone

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/guide/Руководство_текст.md'
DEST = ROOT / 'ASTER_Подробное_руководство.docx'
IMAGES = ROOT / 'docs/guide/images'
QA = ROOT / 'docs/guide/qa'
CROPS = {
    'full': (0, 0, 1, 1),
    'installer': (.012, .012, .685, .425),
    'portfolio': (.085, .280, .627, .392),
    'matrix': (.085, .682, .627, .240),
    'settings': (.725, .280, .180, .520),
    'stress': (.085, .429, .627, .176),
    'result': (.085, .280, .830, .618),
    'histogram': (.085, .495, .428, .345),
    'trajectories': (.525, .495, .380, .345),
    'history': (.085, .278, .830, .595),
    'validation': (.085, .272, .630, .456),
    'nodes': (.085, .280, .830, .440),
}


def el(tag, **attrs):
    node = OxmlElement(tag)
    for name, value in attrs.items():
        node.set(qn(name) if ':' in name else name, str(value))
    return node


def configure_font(style, name='Times New Roman', size=11.5, bold=False):
    style.font.name = name
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'csTheme'):
        fonts.attrib.pop(qn('w:' + attr), None)
    for which in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        fonts.set(qn('w:' + which), name)
    style.element.get_or_add_rPr().append(el('w:lang', **{'w:val': 'ru-RU'}))


def field(p, code, placeholder=''):
    r = p.add_run()._r
    r.append(el('w:fldChar', **{'w:fldCharType': 'begin'}))
    instruction = el('w:instrText')
    instruction.set(qn('xml:space'), 'preserve')
    instruction.text = code
    r.append(instruction)
    r.append(el('w:fldChar', **{'w:fldCharType': 'separate'}))
    if placeholder:
        r.append(el('w:t'))
        r[-1].text = placeholder
    r.append(el('w:fldChar', **{'w:fldCharType': 'end'}))


def text_runs(p, text, wrap_urls=False):
    # URL остаётся полной и кликабельной; команды оформляются отдельно.
    parts = re.split(r'(https?://[^\s]+)', text)
    for part in parts:
        if re.fullmatch(r'https?://[^\s]+', part or ''):
            relation = p.part.relate_to(part,
                'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',
                is_external=True)
            link = el('w:hyperlink', **{'r:id': relation})
            run = el('w:r')
            props = el('w:rPr')
            props.append(el('w:color', **{'w:val': '17466A'}))
            props.append(el('w:u', **{'w:val': 'single'}))
            run.append(props)
            display_lines = [part]
            if wrap_urls and len(part) > 60:
                display_lines = []
                rest = part
                while len(rest) > 60:
                    split = max(rest.rfind('/', 10, 60), rest.rfind('-', 10, 60)) + 1
                    if split < 11:
                        split = 55
                    display_lines.append(rest[:split])
                    rest = rest[split:]
                display_lines.append(rest)
            for n, display_line in enumerate(display_lines):
                if n:
                    run.append(el('w:br'))
                node = el('w:t')
                node.text = display_line
                run.append(node)
            link.append(run)
            p._p.append(link)
        elif part:
            p.add_run(part)


def add_table(doc, rows, width):
    cols = len(rows[0])
    table = doc.add_table(rows=0, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    if cols == 2:
        fractions = [.32, .68]
        if rows[0][0] in ('Файл', 'Файл или папка', 'Официальный материал', 'Материал'):
            fractions = [.40, .60]
    elif cols == 3:
        fractions = [.24, .35, .41]
    elif cols == 4:
        fractions = [.28, .24, .24, .24]
    else:
        fractions = [1 / cols] * cols
    for col, fraction in zip(table.columns, fractions):
        col.width = Mm(width * fraction)
    props = table._tbl.tblPr
    props.append(el('w:tblW', **{'w:w': int(width * 56.6929), 'w:type': 'dxa'}))
    margins = el('w:tblCellMar')
    for side in ('top', 'bottom'):
        margins.append(el('w:' + side, **{'w:w': '95', 'w:type': 'dxa'}))
    for side in ('left', 'right'):
        margins.append(el('w:' + side, **{'w:w': '115', 'w:type': 'dxa'}))
    props.append(margins)
    borders = el('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        borders.append(el('w:' + side, **{'w:val': 'single', 'w:sz': '4', 'w:color': 'CFD4D5'}))
    props.append(borders)
    for n, values in enumerate(rows):
        assert len(values) == cols, values
        row = table.add_row()
        row._tr.get_or_add_trPr().append(el('w:cantSplit'))
        if n == 0:
            row._tr.get_or_add_trPr().append(el('w:tblHeader'))
        for cell, value, fraction in zip(row.cells, values, fractions):
            cell.width = Mm(width * fraction)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell._tc.get_or_add_tcPr().append(el('w:shd', **{
                'w:fill': '364341' if n == 0 else ('F3F5F4' if n % 2 == 0 else 'FFFFFF')}))
            p = cell.paragraphs[0]
            p.style = 'Guide Table'
            text_runs(p, value, wrap_urls=True)
            if n == 0:
                p.paragraph_format.keep_with_next = True
                for run in p.runs:
                    run.bold = True
                    run.font.color.rgb = RGBColor(255, 255, 255)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.line_spacing = Pt(3)
    p.add_run().font.size = Pt(3)
    return table


def add_figure(doc, marker, index, width):
    filename, caption, preset = [v.strip() for v in marker.split('|')]
    path = IMAGES / filename
    crop = CROPS[preset]
    with Image.open(path) as im:
        pixw, pixh = im.size
    left, top, cropw, croph = crop
    ratio = pixw * cropw / (pixh * croph)
    mmw = min(width, 118 * ratio)
    mmh = mmw / ratio
    p = doc.add_paragraph(style='Guide Figure')
    shape = p.add_run().add_picture(str(path), width=Mm(mmw), height=Mm(mmh))
    shape._inline.docPr.set('descr', caption)
    shape._inline.docPr.set('name', f'Рисунок {index} {caption}')
    if preset != 'full':
        fill = shape._inline.xpath('.//pic:blipFill')[0]
        rect = el('a:srcRect', l=int(left * 100000), t=int(top * 100000),
                  r=int((1 - left - cropw) * 100000), b=int((1 - top - croph) * 100000))
        fill.insert(1, rect)
    cp = doc.add_paragraph(style='Caption')
    text_runs(cp, f'Рисунок {index} – {caption}')
    return {'number': index, 'file': path.relative_to(ROOT).as_posix(),
            'caption': caption, 'crop': preset, 'nativeWordCrop': list(crop),
            'sourcePixels': [pixw, pixh], 'displayMm': [round(mmw, 2), round(mmh, 2)],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    text = SOURCE.read_text(encoding='utf-8')
    assert '\u2014' not in text, 'Длинное тире в тексте руководства'
    lines = text.splitlines()
    doc = Document()
    section = doc.sections[0]
    # Новое руководство не является ПЗ; используется отдельный книжный макет.
    section.page_width = Mm(215.9)
    section.page_height = Mm(279.4)
    section.left_margin = section.right_margin = Mm(18)
    section.top_margin = Mm(17)
    section.bottom_margin = Mm(17)
    section.header_distance = Mm(7)
    section.footer_distance = Mm(8)
    section.different_first_page_header_footer = True
    width = 179.9
    normal = doc.styles['Normal']
    configure_font(normal)
    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(5)
    pf.line_spacing = 1.08
    pf.widow_control = True
    pf.keep_together = False
    for name, size in [('Title', 28), ('Subtitle', 16), ('Heading 1', 17),
                       ('Heading 2', 14), ('Heading 3', 12), ('Caption', 10.5)]:
        style = doc.styles[name]
        configure_font(style, size=size, bold=name.startswith('Heading'))
        style.font.italic = False
        for border in style.element.xpath('.//w:pBdr'):
            border.getparent().remove(border)
        style.paragraph_format.space_before = Pt(10 if name.startswith('Heading') else 0)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = name.startswith('Heading')
        style.paragraph_format.keep_together = True
        if name.startswith('Heading'):
            style.element.get_or_add_pPr().append(el('w:suppressAutoHyphens'))
    for level in (1, 2):
        name = 'TOC ' + str(level)
        style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH) if name not in doc.styles else doc.styles[name]
        configure_font(style, size=10.5)
        style.paragraph_format.space_after = Pt(1)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.line_spacing = 1.0
        style.paragraph_format.left_indent = Mm(5 if level == 2 else 0)
        style.paragraph_format.keep_with_next = False
    for name, font, size in [('Guide Code', 'Consolas', 9.5), ('Guide Step', 'Times New Roman', 11.5),
                              ('Guide Bullet', 'Times New Roman', 11.5), ('Guide Table', 'Times New Roman', 10.5),
                              ('Guide Figure', 'Times New Roman', 11.5)]:
        style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = normal
        configure_font(style, font, size)
        style.paragraph_format.keep_together = True
        if name in ('Guide Step', 'Guide Bullet'):
            style.paragraph_format.left_indent = Mm(6)
            style.paragraph_format.first_line_indent = Mm(-6)
        if name == 'Guide Code':
            style.paragraph_format.left_indent = Mm(3)
            style.paragraph_format.line_spacing = 1.04
            style.paragraph_format.space_after = Pt(2)
            style.element.get_or_add_pPr().append(el('w:suppressAutoHyphens'))
        if name == 'Guide Table':
            style.paragraph_format.line_spacing = 1.04
            style.paragraph_format.space_after = Pt(0)
        if name == 'Guide Figure':
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            style.paragraph_format.space_before = Pt(5)
            style.paragraph_format.space_after = Pt(4)
            style.paragraph_format.keep_with_next = True
    doc.styles['Caption'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.styles['Caption'].paragraph_format.space_after = Pt(9)
    for name in ('Header', 'Footer'):
        configure_font(doc.styles[name], size=9)
    ct = doc.styles.add_style('Guide Contents Title', WD_STYLE_TYPE.PARAGRAPH)
    ct.base_style = normal
    configure_font(ct, size=17, bold=True)
    ct.paragraph_format.space_after = Pt(10)
    hp = section.header.paragraphs[0]
    hp.add_run('ASTER  •  Руководство по запуску и работе')
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    field(footer, ' PAGE ')
    doc.core_properties.title = 'Подробное руководство ASTER'
    doc.core_properties.subject = 'Запуск через Docker и Visual Studio работа с портфелем и доработка'
    doc.core_properties.author = 'Бокая Д. В.'
    doc.core_properties.keywords = 'ASTER Docker Visual Studio руководство'
    doc.settings.element.append(el('w:updateFields', **{'w:val': 'true'}))
    # Удаляются декоративные границы встроенных стилей, в том числе у предков Title.
    for border in doc.styles.element.xpath('.//w:pBdr'):
        border.getparent().remove(border)

    title = doc.add_paragraph('Подробное руководство ASTER', style='Title')
    title.paragraph_format.space_before = Pt(68)
    title.paragraph_format.space_after = Pt(17)
    doc.add_paragraph('Запуск программы и работа с портфелем\nРазработка и отладка', style='Subtitle')
    cp = doc.add_paragraph('Курсовой проект Бокой Д. В.\nГруппа ИТД-41')
    cp.paragraph_format.space_before = Pt(19)
    doc.add_paragraph('Стресс-тестирование портфеля ценных бумаг\nс учётом прогноза')
    cp = doc.add_paragraph('Для первого запуска и дальнейшей разработки')
    cp.paragraph_format.space_before = Pt(20)
    cp.add_run('\nДва маршрута: Docker и Visual Studio')
    doc.add_paragraph('От подготовки папки до расчёта, экспорта,\nотладки и резервного копирования')
    cp = doc.add_paragraph('Версия от 10 октября 2026 года')
    cp.paragraph_format.space_before = Pt(18)
    doc.add_page_break()
    tp = doc.add_paragraph('Содержание', style='Guide Contents Title')
    # Содержание само себя не включает.
    tp._p.get_or_add_pPr().append(el('w:outlineLvl', **{'w:val': '9'}))
    field(doc.add_paragraph(), ' TOC \\o "1-2" \\h \\z \\u ', 'Содержание обновляется в Microsoft Word')

    start = next(i for i, line in enumerate(lines) if line == '## 1 Как пользоваться руководством')
    i = start
    figures = []
    headings = []
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line == '@@PAGE':
            i += 1
            continue
        if line.startswith('## '):
            value = line[3:]
            # Пунктуация в нумерации сохраняется, названия оформлены спокойно.
            value = value.replace(': ', ' ').replace(' / ', ' и ')
            number = value.split()[0]
            level = 2 if '.' in number else 1
            p = doc.add_paragraph(value, style='Heading ' + str(level))
            if level == 1:
                p.paragraph_format.page_break_before = True
            headings.append({'level': level, 'text': value})
        elif line.startswith('### '):
            doc.add_paragraph(line[4:].replace(': ', ' '), style='Heading 3')
        elif line.startswith('@@FIG '):
            figures.append(add_figure(doc, line[6:], len(figures) + 1, width))
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            add_table(doc, rows, width)
            continue
        elif line.startswith('```'):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i])
                i += 1
            for n, code in enumerate(block):
                p = doc.add_paragraph(code, style='Guide Code')
                p.paragraph_format.keep_with_next = n < len(block) - 1 and len(block) <= 8
                if n == 0:
                    p.paragraph_format.space_before = Pt(3)
                if n == len(block) - 1:
                    p.paragraph_format.space_after = Pt(8)
        else:
            if re.match(r'^\d+\. ', line):
                p = doc.add_paragraph(style='Guide Step')
            elif line.startswith('- '):
                p = doc.add_paragraph(style='Guide Bullet')
                line = '• ' + line[2:]
            else:
                p = doc.add_paragraph()
            text_runs(p, line)
        i += 1
    doc.save(DEST)
    report = {'date': datetime.now(timezone.utc).isoformat(), 'source': SOURCE.relative_to(ROOT).as_posix(),
              'document': DEST.relative_to(ROOT).as_posix(), 'paragraphs': len(doc.paragraphs),
              'tables': len(doc.tables), 'figures': figures, 'headings': headings,
              'pzOpenedOrWritten': False, 'pageFormat': 'Letter', 'bodyFont': 'Times New Roman 11.5 pt'}
    QA.mkdir(parents=True, exist_ok=True)
    (QA / 'build-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'document': str(DEST), 'paragraphs': len(doc.paragraphs), 'tables': len(doc.tables),
                      'figures': len(figures), 'headingEntries': len(headings)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
