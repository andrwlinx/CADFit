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


slide('CADFit v2: CAD files that actually work',
      ['Goal: turn a 3D shape into an editable CAD program',
       'Update, Oct 23 2026'],
      bullets_top=Inches(1.6), size=24)

slide('The problem',
      ['The old system often produced CAD that looked right but was broken',
       'Broken = the program fails to build, or the solid is invalid in CAD software',
       'A broken file is useless to an engineer, so we score it as 0'],
      bullets_top=Inches(1.6), size=24)

slide('The fix: test every answer before handing it over',
      ['Before, the first answer was delivered without being checked',
       'Now: build every candidate, check it, repair it if needed, and deliver the best one that works'],
      image='simple_pipeline.png', img_h=Inches(2.6), size=20)

slide('Example 1: merging overlapping pieces',
      ['The old answer stacked 208 overlapping pieces, so CAD software rejects it',
       'v2 merges them into one clean solid'],
      image='simple_00642725.png', img_h=Inches(4.2), size=20)

slide('Example 2: repairing broken pieces',
      ['2 pieces were broken, so the whole answer counted as 0',
       'v2 repairs them; the shape stays the same and now works'],
      image='simple_00232213.png', img_h=Inches(4.2), size=20)

slide('Results so far (60 test parts)',
      ['Score: 0.81 -> 0.95.  Broken outputs: 8 -> 1.  The improvement is statistically clear',
       'Most of the gain comes from no longer handing over broken files'],
      image='simple_results.png', img_h=Inches(3.9), size=20)

slide('What is next',
      ['Oct 24: outside review of the method',
       'Then: final test on 300 new parts the system has never seen',
       'Closest competing work (CADFather, Oct 2026) checks answers too, but does not repair broken ones',
       'Questions: is this a strong enough angle? Which venue should we target?'],
      bullets_top=Inches(1.6), size=24)

out = os.path.join(HERE, 'CADFit_v2_update.pptx')
prs.save(out)
print(out, len(prs.slides), 'slides')
