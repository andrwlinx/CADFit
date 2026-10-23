"""Plain slides for the v2 update: white background, text and figures only.

  ~/.claude/office-skills/venv/bin/python bench/figures/v2_2026-10-23/make_slides.py
"""
import os

from pptx import Presentation
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, lines, size=18, bold_first=False):
    tf = slide.shapes.add_textbox(x, y, w, h).text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.bold = bold_first and i == 0
        p.space_after = Pt(6)
    return tf


def slide(title, bullets=(), image=None, img_top=Inches(1.3), img_h=None, bullets_top=None, size=18):
    s = prs.slides.add_slide(BLANK)
    text(s, Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.8), [title], size=30, bold_first=True)
    top = img_top
    if image:
        path = os.path.join(HERE, image)
        pic = s.shapes.add_picture(path, Inches(0.6), top, width=Inches(12.1))
        if img_h and pic.height > img_h:  # fit height, keep aspect, center
            ratio = img_h / pic.height
            pic.height, pic.width = int(pic.height * ratio), int(pic.width * ratio)
            pic.left = int((W - pic.width) / 2)
        top = Emu(pic.top + pic.height + Inches(0.2))
    if bullets:
        text(s, Inches(0.6), bullets_top or top, Inches(12.1), H - (bullets_top or top) - Inches(0.3),
             list(bullets), size=size)
    return s


slide('CADFit++ v2: execution-verified CAD delivery',
      ['Update, Oct 23 2026',
       'Mesh -> CadQuery program reverse engineering',
       'All numbers are on the 60-part development cohort; the 300-part held-out run (fresh2) comes after the external review on Oct 24'],
      bullets_top=Inches(1.6), size=22)

slide('Why validity matters: mesh IoU hides failed CAD (pre-v2 pipeline)',
      ['(a) Pre-v2 search arms: the reported mesh scores well while the executed program is unbuilt or OCC-invalid (red counts)',
       '(b) Open-weight agents: CADFit skills vs code-only tools (pre-v2 tools and harness)'],
      image='hero_pre_v2.png', img_h=Inches(4.5), size=16)

slide('v2: run the programs, deliver the best valid one',
      ['Each candidate program is executed; every solid is checked with OCC BRepCheck',
       'Invalid solids are repaired (ShapeFix) or dropped; overlapping .add() bodies are fused',
       'Metric: validity-gated IoU(CAD) = IoU of the delivered program, 0 if it does not build or is invalid'],
      image='pipeline_v2.png', img_h=Inches(4.1), size=16)

slide('Example: fusing overlapping solids (part 00642725)',
      ['The search program stacks 208 solids with .add(); 34 are OCC-invalid and the result is not one solid',
       'v2 executes the fused rewrite: one valid solid, IoU 0.938'],
      image='render_00642725_fuse.png', img_h=Inches(4.3), size=16)

slide('Example: repairing invalid solids (part 00232213)',
      ['2 of 138 solids fail OCC validity, so the program scores 0 under the gate',
       'The repair pass fixes them: same geometry, valid, IoU 0.873'],
      image='render_00232213_repair.png', img_h=Inches(4.3), size=16)

slide('Development results (60 parts, dev4 run)',
      ['Validity-gated IoU(CAD): pre-v2 code 0.808 -> v2 0.949',
       'Paired gain +0.141, 95% CI [+0.062, +0.233], 13 parts better / 2 worse, Holm-corrected p < 0.001',
       'Invalid or missing deliveries: 8 -> 1',
       'Most of the gain is avoiding zeros: on parts both versions build validly, the gain is +0.035',
       'Fixes after round-1 review: +0.037, p = 0.10 after correction (suggestive only)',
       'Since then fixed: an out-of-memory part that killed neighbouring jobs, and a judge error on non-watertight targets',
       'Clean re-run (dev5) with all fixes is in progress; results chart to follow'],
      bullets_top=Inches(1.5), size=20)

slide('Related work and next steps',
      ['Closest work: CADFather (arXiv 2610.09127, Oct 6): an agent that executes candidates and keeps the best valid one',
       'It has no repair step and no OCC B-rep validity check; MIRAGE-CAD reports 55-70% build success, so validity is the bottleneck',
       'Our angle: OCC validity + repair, and a controlled study of agent toolsets under matched budgets',
       'Next: external review (Oct 24), then the 300-part held-out run for the pipeline and the open-weight agents',
       'Questions: is this angle enough against CADFather? Target venue? Run CADFather head-to-head on CADBench?'],
      bullets_top=Inches(1.5), size=20)

out = os.path.join(HERE, 'CADFit_v2_update.pptx')
prs.save(out)
print(out, len(prs.slides), 'slides')
