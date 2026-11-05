"""Build the common editable practice report; refresh fields in Word afterwards."""

from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor


FONT = "Times New Roman"
BLACK = RGBColor(0, 0, 0)
CONTROL_ID = 100


def el(local_name, **attrs):
    node = OxmlElement("w:" + local_name)
    for key, value in attrs.items():
        node.set(qn("w:" + key), str(value))
    return node


def configure_style(style, size=14, *, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                    indent=12.5, line=1.5, caps=False, before=0, after=0):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = BLACK
    style.font.all_caps = caps
    rpr = style.element.get_or_add_rPr()
    cs_size = rpr.find(qn("w:szCs"))
    if cs_size is not None:
        cs_size.set(qn("w:val"), str(size * 2))
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = el("rFonts")
        rpr.insert(0, fonts)
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + key), FONT)
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn("w:" + key), None)
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        rpr.append(el("lang", val="ru-RU"))
    pf = style.paragraph_format
    pf.alignment = align
    pf.first_line_indent = Mm(indent)
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    style.element.attrib.pop(qn("w:customStyle"), None)
    for item in list(style.element.findall(qn("w:autoRedefine"))):
        style.element.remove(item)


def new_style(doc, name, **kw):
    style = doc.styles[name] if name in doc.styles else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles["Normal"]
    configure_style(style, **kw)
    return style


def numbering(doc):
    root = doc.part.numbering_part.element
    aid = max([int(n.get(qn("w:abstractNumId"))) for n in root.findall(qn("w:abstractNum"))] + [0]) + 1
    nid = max([int(n.get(qn("w:numId"))) for n in root.findall(qn("w:num"))] + [0]) + 1
    abstract = el("abstractNum", abstractNumId=aid)
    abstract.append(el("multiLevelType", val="multilevel"))
    for level in range(3):
        item = el("lvl", ilvl=level)
        item.extend([el("start", val=1), el("numFmt", val="decimal"),
                     el("pStyle", val=f"Heading{level + 1}"),
                     el("lvlText", val=".".join(f"%{i + 1}" for i in range(level + 1)) + "."),
                     el("lvlJc", val="left"), el("suff", val="space")])
        item.append(el("pPr"))
        abstract.append(item)
    root.append(abstract)
    instance = el("num", numId=nid)
    instance.append(el("abstractNumId", val=aid))
    root.append(instance)
    for level in range(3):
        ppr = doc.styles[f"Heading {level + 1}"].element.get_or_add_pPr()
        prop = el("numPr")
        prop.extend([el("ilvl", val=level), el("numId", val=nid)])
        ppr.append(prop)


def text_control(paragraph, tag, label, text="____________________", *, multiline=False):
    global CONTROL_ID
    CONTROL_ID += 1
    control = el("sdt")
    props = el("sdtPr")
    props.extend([el("alias", val=label), el("tag", val=tag), el("id", val=CONTROL_ID),
                  el("text", multiLine="1" if multiline else "0")])
    content = el("sdtContent")
    run = el("r")
    run.append(el("t"))
    run[-1].text = text
    content.append(run)
    control.extend([props, content])
    paragraph._p.append(control)
    return control


def field(paragraph, code, cached="1", *, bookmark=None):
    if bookmark:
        paragraph._p.append(el("bookmarkStart", id=bookmark[0], name=bookmark[1]))
    for node in [el("fldChar", fldCharType="begin"), el("instrText"),
                 el("fldChar", fldCharType="separate"), el("t"),
                 el("fldChar", fldCharType="end")]:
        run = el("r")
        if node.tag == qn("w:instrText"):
            node.set(qn("xml:space"), "preserve")
            node.text = " " + code + " "
        if node.tag == qn("w:t"):
            node.text = cached
        run.append(node)
        paragraph._p.append(run)
    if bookmark:
        paragraph._p.append(el("bookmarkEnd", id=bookmark[0]))


def response(doc, label, tag, lines=2):
    p = doc.add_paragraph(style="Field label")
    p.add_run(label).bold = True
    for i in range(lines):
        p = doc.add_paragraph(style="Response")
        text_control(p, f"{tag}_{i + 1}", label, "____________________________________________________", multiline=True)


def heading(doc, text, level=1, *, new_page=False):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    p.paragraph_format.page_break_before = new_page
    return p


def figure_slot(doc, label, tag, number, bookmark_name):
    p = doc.add_paragraph(label, style="Field label")
    p.paragraph_format.keep_with_next = True
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Mm(160)
    table.cell(0, 0).width = Mm(160)
    table.rows[0].height = Mm(60)
    table.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    table.rows[0]._tr.get_or_add_trPr().append(el("cantSplit"))
    props = table._tbl.tblPr
    borders = el("tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(el(side, val="single", sz=4, color="B7B7B7"))
    props.append(borders)
    margins = el("tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        margins.append(el(side, w=100, type="dxa"))
    props.append(margins)
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.style = "Picture placeholder"
    p.paragraph_format.keep_with_next = True
    control = text_control(p, tag, label, "Вставить собственный рисунок")
    control.find(qn("w:sdtPr")).remove(control.find(qn("w:sdtPr")).find(qn("w:text")))
    p = doc.add_paragraph(style="Caption")
    p.add_run("Рисунок ")
    field(p, r"SEQ Рисунок \* ARABIC", str(number), bookmark=(number, bookmark_name))
    p.add_run(" — " + label[:1].lower() + label[1:])
