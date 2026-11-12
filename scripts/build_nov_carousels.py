#!/usr/bin/env python3
"""Render the six exact-copy Nov 16–29 carousels; never edits the queue.

The approved brief and subsequent user clarifications live in batch_nov16_29/.
All text is loaded from that manifest. Geometry is rendered at 2x then exported
as a 1080x1350 quality-95 JPEG with an embedded sRGB ICC profile.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H, SCALE, MARGIN = 1080, 1350, 2, 88
INK, DEEP, FOREST = "#07150F", "#0D2119", "#315746"
PAPER, LIME, MINT = "#F8F8F4", "#B8FF5A", "#9DF3C5"
THEMES = {
    "paper": dict(bg=PAPER, fg=INK, accent=FOREST, rule="#D9E0D9", motif="#E7EDE3"),
    "dark": dict(bg=DEEP, fg=PAPER, accent=LIME, rule=FOREST, motif="#17372A"),
    "lime": dict(bg=LIME, fg=INK, accent=INK, rule="#81B83B", motif="#A7EA50"),
}
COVER_THEMES = {"N02": "paper", "N03": "dark", "N06": "paper", "N09": "dark", "N10": "lime", "N13": "dark"}


@lru_cache(maxsize=None)
def font(size: int, weight: str = "Extrabold"):
    return ImageFont.truetype(str(ROOT / "brand/03_Fonts" / f"Manrope-{weight}.ttf"), round(size * SCALE))


def normalized(text: str) -> str:
    return " ".join(text.split())


def word_count(text: str) -> int:
    return sum(bool(re.search(r"\w|₹", word)) for word in text.split())


DISPLAY_LAYOUTS = {
    ("N02", 4): {
        "display_text": "Bank 3 cheezein dekhta hai:\n1. Kamai aur ITR (income tax return)\n2. Purani EMIs\n3. Property ke kagaz aur title",
        "description": "User-requested heading and three separately spaced numbered entries, each on one line.",
        "kind": "line_breaks",
    },
    ("N06", 4): {
        "display_text": "Par total byaaj:\nPersonal loan ₹13,77,250\nLAP ₹31,37,623\nKam EMI ka matlab sasta loan nahi.",
        "description": "User-requested heading, two separate loan/interest lines, and closing line; remove the middot only here.",
        "kind": "explicit_user_text_layout",
    },
}


def assert_line_baselines(line: dict) -> None:
    """Reject floated tokens, including metadata that hides a different draw origin."""
    baseline = line["baseline_y"]
    baseline_px = round(baseline * SCALE)
    assert line["anchor"] == "ls", ("line anchor", line)
    assert line["draw_origin"][1] == baseline, ("line draw origin", line)
    assert line["pixel_origin"][1] == baseline_px, ("line pixel baseline", line)
    assert line["words"], "A rendered line needs per-word baseline records."
    for word in line["words"]:
        assert word["anchor"] == "ls", ("word anchor", word)
        assert word["baseline_y"] == baseline, ("word baseline", word)
        assert word["line_baseline_y"] == baseline, ("word line baseline", word)
        assert word["draw_origin"][1] == baseline, ("actual word draw origin", word)
        assert word["pixel_origin"][1] == baseline_px, ("actual word pixel baseline", word)
        assert word["baseline_px"] == baseline_px, ("word baseline pixels", word)


class Canvas:
    def __init__(self, theme: str):
        self.theme = theme
        self.colors = THEMES[theme]
        self.image = Image.new("RGB", (W * SCALE, H * SCALE), self.colors["bg"])
        self.draw = ImageDraw.Draw(self.image)
        self.elements = []

    def rectangle(self, box, fill, radius=0):
        box = tuple(round(v * SCALE) for v in box)
        if radius:
            self.draw.rounded_rectangle(box, radius=radius * SCALE, fill=fill)
        else:
            self.draw.rectangle(box, fill=fill)

    def rule(self, y: int, x1=MARGIN, x2=W-MARGIN, color=None, width=2):
        self.draw.line((x1*SCALE, y*SCALE, x2*SCALE, y*SCALE), fill=color or self.colors["rule"], width=width*SCALE)

    def arc_motif(self, lower=True):
        # Derived from the kit's open concentric arc motif, never a redrawn logo.
        cx, cy = (1060, 1275) if lower else (1080, 170)
        for radius in (180, 260, 340):
            self.draw.arc(tuple(round(v*SCALE) for v in (cx-radius,cy-radius,cx+radius,cy+radius)), 42, 318,
                          fill=self.colors["motif"], width=13*SCALE)

    def width(self, text: str, size: int, weight="Extrabold") -> float:
        return self.draw.textlength(text, font=font(size,weight))/SCALE

    def wrap(self, text: str, size: int, width: float, weight="Extrabold"):
        lines=[]
        for paragraph in text.split("\n"):
            line=""
            for word in paragraph.split():
                proposed=(line+" "+word).strip()
                if line and self.width(proposed,size,weight)>width:
                    lines.append(line)
                    line=word
                else:
                    line=proposed
            lines.append(line)
        if any(self.width(line,size,weight)>width+.1 for line in lines):
            return None
        assert normalized(" ".join(lines))==normalized(text)
        return lines

    def ink_bounds(self, line, x, baseline, size, weight):
        box=self.draw.textbbox((round(x*SCALE),round(baseline*SCALE)),line,font=font(size,weight),anchor="ls")
        return [round(v/SCALE,2) for v in box]

    def fit(self, text, box, max_size, min_size, weight="Extrabold", spacing=1.14):
        x1,y1,x2,y2=box
        for size in range(max_size,min_size-1,-1):
            lines=self.wrap(text,size,x2-x1,weight)
            if not lines:
                continue
            leading=round(size*spacing)
            ascent=font(size,weight).getmetrics()[0]/SCALE
            bounds=[self.ink_bounds(line,x1,ascent+n*leading,size,weight) for n,line in enumerate(lines)]
            if max(b[3] for b in bounds)-min(b[1] for b in bounds)<=y2-y1:
                return size,lines,leading
        raise ValueError(f"Copy does not fit at {min_size}px: {text}")

    def draw_baseline_line(self, text, x, baseline, size, weight, fill=None, accent_numbers=False):
        """Draw every word at the same actual raster baseline, never its own ink top."""
        face=font(size,weight)
        baseline_px=round(baseline*SCALE)
        baseline=baseline_px/SCALE
        words=[]
        for match in re.finditer(r"\S+",text):
            token=match.group()
            # Measure the complete prefix so spacing follows the original line.
            x_px=round(x*SCALE+self.draw.textlength(text[:match.start()],font=face))
            origin=(x_px,baseline_px)
            color=self.colors["accent"] if accent_numbers and self.theme=="dark" and re.search(r"\d|₹",token) else (fill or self.colors["fg"])
            self.draw.text(origin,token,font=face,fill=color,anchor="ls")
            ink=self.draw.textbbox(origin,token,font=face,anchor="ls")
            words.append(dict(text=token,bounds=[round(v/SCALE,2) for v in ink],
                              baseline_y=baseline,line_baseline_y=baseline,baseline_px=baseline_px,
                              draw_origin=[x_px/SCALE,baseline],pixel_origin=list(origin),anchor="ls"))
        bounds=[min(w["bounds"][0] for w in words),min(w["bounds"][1] for w in words),
                max(w["bounds"][2] for w in words),max(w["bounds"][3] for w in words)]
        record=dict(text=text,bounds=bounds,baseline_y=baseline,anchor="ls",
                    draw_origin=[round(x*SCALE)/SCALE,baseline],pixel_origin=[round(x*SCALE),baseline_px],
                    font_size=size,weight=weight,font_path=f"brand/03_Fonts/Manrope-{weight}.ttf",
                    font_metrics=dict(ascent=face.getmetrics()[0]/SCALE,descent=face.getmetrics()[1]/SCALE),
                    words=words)
        assert_line_baselines(record)
        return record

    def record_element(self, role, text, records, size, weight, display_text=None, display_override=None):
        bounds=[min(b["bounds"][0] for b in records),min(b["bounds"][1] for b in records),
                max(b["bounds"][2] for b in records),max(b["bounds"][3] for b in records)]
        assert all(0<=bounds[i]<=(W if i%2==0 else H) for i in range(4)), (role,bounds)
        element=dict(role=role,text=text,display_text=display_text or text,bounds=bounds,
                     font_size=size,weight=weight,lines=records)
        if display_override:
            element["display_override"]=display_override
        self.elements.append(element)
        return bounds

    def block(self, role, text, box, max_size, min_size, weight="Extrabold", spacing=1.14,
              fill=None, valign="top", accent_numbers=False):
        size,lines,leading=self.fit(text,box,max_size,min_size,weight,spacing)
        x,y,x2,y2=box
        ascent=font(size,weight).getmetrics()[0]/SCALE
        relative=[self.ink_bounds(line,x,ascent+n*leading,size,weight) for n,line in enumerate(lines)]
        top=min(b[1] for b in relative)
        bottom=max(b[3] for b in relative)
        offset=y-top
        if valign=="center":
            offset+=(y2-y-(bottom-top))/2
        records=[]
        for n,line in enumerate(lines):
            records.append(self.draw_baseline_line(line,x,ascent+n*leading+offset,size,weight,fill,accent_numbers))
        return self.record_element(role,text,records,size,weight)

    def single_line_size(self,text,width,max_size,min_size,weight="Extrabold"):
        for size in range(max_size,min_size-1,-1):
            if self.width(text,size,weight)<=width:
                return size
        raise ValueError(f"Single-line copy does not fit at {min_size}px: {text}")

    def requested_display_layout(self,item,slide):
        spec=DISPLAY_LAYOUTS[(item["id"],slide["number"])]
        texts=spec["display_text"].splitlines()
        width=W-2*MARGIN
        if item["id"]=="N02":
            heading_size=self.single_line_size(texts[0],width,72,44)
            entry_size=min(self.single_line_size(t,width,64,38) for t in texts[1:])
            sizes=[heading_size,entry_size,entry_size,entry_size]
            tops=[330,530,710,890]
        else:
            heading_size=self.single_line_size(texts[0],width,80,54)
            amount_size=min(self.single_line_size(t,width,80,54) for t in texts[1:3])
            closing_size=self.single_line_size(texts[3],width,62,40)
            sizes=[heading_size,amount_size,amount_size,closing_size]
            tops=[330,525,710,945]
        records=[]
        for text,size,top in zip(texts,sizes,tops):
            # Shared ascent gives a typographic line box; it is not token-specific.
            ascent=font(size,"Extrabold").getmetrics()[0]/SCALE
            records.append(self.draw_baseline_line(text,MARGIN,top+ascent,size,"Extrabold",accent_numbers=True))
        override=dict(requested_by_user=True,kind=spec["kind"],canonical_text=slide["text"],
                      display_text=spec["display_text"],description=spec["description"])
        self.record_element("body",slide["text"],records,max(sizes),"Extrabold",spec["display_text"],override)

    def save(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        self.image.resize((W,H),Image.Resampling.LANCZOS).save(path,"JPEG",quality=95,optimize=True,subsampling=0,icc_profile=srgb)
        assert path.stat().st_size<8*1024*1024


def cover(item,slide):
    c=Canvas(COVER_THEMES[item["id"]])
    c.arc_motif()
    c.block("series",item["series"],(MARGIN,112,W-MARGIN,160),28,26,"Bold",fill=c.colors["accent"])
    c.rule(196)
    c.block("body",slide["text"],(MARGIN,300,W-MARGIN,1100),220,90,spacing=1.06,valign="center")
    c.rule(1200)
    c.block("website","crednest.io",(MARGIN,1235,W-MARGIN,1285),32,32,"Bold")
    return c


def interior_theme(item_id,number):
    # Numerically dense cases use alternating dark and cream pages for hierarchy.
    if item_id in {"N02","N09"}:
        return "dark" if number in {2,4} else "paper"
    return "dark" if number%2==0 else "paper"


def interior(item,slide,data):
    is_last=bool(slide.get("cta"))
    numeric=bool(re.search(r"\d",slide["text"]))
    c=Canvas(interior_theme(item["id"],slide["number"]))
    c.arc_motif(lower=not is_last)
    # Pure geometry is not an added headline, slide count or series label.
    c.rectangle((MARGIN,105,MARGIN+120,113),LIME if c.theme=="dark" else FOREST,4)
    if numeric:
        c.block("example_tag",data["example_tag"],(MARGIN,152,W-MARGIN,192),25,25,"Medium",fill=c.colors["accent"])
    main_box=(MARGIN,250,W-MARGIN,865 if is_last else 1120)
    if (item["id"],slide["number"]) in DISPLAY_LAYOUTS:
        c.requested_display_layout(item,slide)
    else:
        c.block("body",slide["text"],main_box,116 if not is_last else 103,62,spacing=1.16,
                valign="center",accent_numbers=numeric)
    if is_last:
        cta_bg,cta_fg=(LIME,INK) if c.theme=="dark" else (DEEP,PAPER)
        c.rectangle((MARGIN,930,W-MARGIN,1100),cta_bg,22)
        c.block("cta",slide["cta"],(MARGIN+32,957,W-MARGIN-32,1074),46,34,"Bold",spacing=1.12,fill=cta_fg,valign="center")
        c.rule(1153)
        c.block("footer",data["disclaimer"],(MARGIN,1182,W-MARGIN,1298),27,25,"Medium",spacing=1.2)
    return c


def contact_sheet(slides,path,columns=5,thumb_width=216):
    pad,caption_h=12,28
    thumb_height=round(thumb_width*H/W)
    rows=(len(slides)+columns-1)//columns
    out=Image.new("RGB",(columns*(thumb_width+pad)+pad,rows*(thumb_height+caption_h+pad)+pad),"#E4E8E0")
    draw=ImageDraw.Draw(out)
    label_font=ImageFont.truetype(str(ROOT/"brand/03_Fonts/Manrope-Bold.ttf"),16)
    for index,slide in enumerate(slides):
        x=pad+(index%columns)*(thumb_width+pad)
        y=pad+(index//columns)*(thumb_height+caption_h+pad)
        image=Image.open(ROOT/slide["path"]).convert("RGB")
        out.paste(image.resize((thumb_width,thumb_height),Image.Resampling.LANCZOS),(x,y))
        draw.text((x,y+thumb_height+5),f'{slide["id"]} / {slide["slide"]:02d}',font=label_font,fill=INK)
    path.parent.mkdir(parents=True,exist_ok=True)
    out.save(path,"JPEG",quality=92,subsampling=0)


def baseline_regressions():
    """Exercise mixed x-heights/descenders and reject a falsely aligned token."""
    canvas=Canvas("dark")
    text="aur tax p.a. se naap EMI ₹13,77,250"
    line=canvas.draw_baseline_line(text,60,260,72,"Extrabold",accent_numbers=True)
    assert_line_baselines(line)
    # A common baseline necessarily gives these mixed glyphs different ink tops.
    assert len({word["bounds"][1] for word in line["words"]})>1, "Fixture must exercise unlike ascenders."
    assert any(word["bounds"][3]>line["baseline_y"] for word in line["words"]), "Fixture must exercise descenders."
    face=font(line["font_size"],line["weight"])
    blank=Image.new("RGB",canvas.image.size,canvas.colors["bg"])
    actual_ink=ImageChops.difference(canvas.image,blank).convert("L")
    for index,word in enumerate(line["words"]):
        expected=canvas.draw.textbbox(tuple(word["pixel_origin"]),word["text"],font=face,anchor="ls")
        assert word["bounds"]==[round(v/SCALE,2) for v in expected], "Recorded ink must match the actual raster origin."
        # Measure actual pixels independently of the recorded textbbox. Isolating
        # each word horizontally catches the old per-token ink-top anchoring.
        left=0 if index==0 else round((line["words"][index-1]["bounds"][2]+word["bounds"][0])*SCALE/2)
        right=W*SCALE if index+1==len(line["words"]) else round((word["bounds"][2]+line["words"][index+1]["bounds"][0])*SCALE/2)
        reference=blank.copy()
        color=canvas.colors["accent"] if re.search(r"\d|₹",word["text"]) else canvas.colors["fg"]
        ImageDraw.Draw(reference).text(tuple(word["pixel_origin"]),word["text"],font=face,fill=color,anchor="ls")
        reference_ink=ImageChops.difference(reference,blank).convert("L")
        region=(left,0,right,H*SCALE)
        assert actual_ink.crop(region).getbbox()==reference_ink.crop(region).getbbox(), "Rendered word pixels must match the common-baseline glyph origin."
    rejected=[]
    for name,field,value in [("float_draw_origin","draw_origin",[line["words"][0]["draw_origin"][0],line["baseline_y"]-1]),
                             ("ink_top_anchor","anchor","lt")]:
        bad=deepcopy(line)
        bad["words"][0][field]=value
        try:
            assert_line_baselines(bad)
        except AssertionError:
            rejected.append(name)
        else:
            raise AssertionError(f"Baseline regression did not reject {name}.")
    return dict(status="passed",mixed_glyph_fixture=text,pixel_glyph_origin_check="passed",negative_fixtures_rejected=rejected,
                anchor="ls",origin_units="final-image pixels; pixel_origin is the 2x raster coordinate")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only",nargs="*",help="Render only the named carousel IDs.")
    parser.add_argument("--self-test",action="store_true",help="Run the mixed-glyph and negative baseline regressions only.")
    args=parser.parse_args()
    baseline_checks=baseline_regressions()
    if args.self_test:
        print(json.dumps(baseline_checks,indent=2))
        return
    data=json.loads((ROOT/"batch_nov16_29/batch.json").read_text(encoding="utf-8"))
    assert not data.get("series_pending"),"Exact series tags must be resolved before rendering."
    report=dict(canvas=[W,H],color_space="sRGB",jpeg_quality=95,supersampling=SCALE,
                text_anchor="ls",origin_units="final-image pixels; pixel_origin is the 2x raster coordinate",
                baseline_regressions=baseline_checks,slides=[])
    items=[i for i in data["items"] if i["type"]=="carousel" and (not args.only or i["id"] in args.only)]
    for item in items:
        for slide in item["slides"]:
            assert word_count(slide["text"])<=25,(item["id"],slide["number"],word_count(slide["text"]))
            c=cover(item,slide) if slide["number"]==1 else interior(item,slide,data)
            path=ROOT/"media"/item["id"]/f'{slide["number"]:02d}.jpg'
            c.save(path)
            expected_roles={"series","body","website"} if slide["number"]==1 else {"body"}
            if slide.get("cta"): expected_roles|={"cta","footer"}
            if slide["number"]>1 and re.search(r"\d",slide["text"]):expected_roles.add("example_tag")
            assert {e["role"] for e in c.elements}==expected_roles
            row=dict(id=item["id"],slide=slide["number"],path=path.relative_to(ROOT).as_posix(),body=slide["text"],
                     cta=slide.get("cta"),example_tag=data["example_tag"] if "example_tag" in expected_roles else None,
                     footer=data["disclaimer"] if "footer" in expected_roles else None,
                     main_body_words=word_count(slide["text"]),theme=c.theme,elements=c.elements,bytes=path.stat().st_size)
            body_element=next(e for e in c.elements if e["role"]=="body")
            row["display_body"]=body_element["display_text"]
            if body_element.get("display_override"):
                row["display_override"]=body_element["display_override"]
            report["slides"].append(row)
            print(f'rendered {row["path"]} ({row["main_body_words"]} body words)')
    reports=ROOT/"reports/nov16-29"
    reports.mkdir(parents=True,exist_ok=True)
    (reports/"carousel-render-manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    contact_sheet(report["slides"],reports/"carousel-all-slides.jpg")
    contact_sheet([s for s in report["slides"] if s["slide"]==1],reports/"carousel-covers.jpg",columns=3,thumb_width=320)
    validation=dict(status="passed",rendered_images=len(report["slides"]),canvas=[W,H],jpeg_quality=95,
                    icc="embedded sRGB",max_file_bytes=max(s["bytes"] for s in report["slides"]),
                    total_bytes=sum(s["bytes"] for s in report["slides"]),
                    max_main_body_words=max(s["main_body_words"] for s in report["slides"]),
                    minimum_main_body_font_size=min(line["font_size"] for s in report["slides"] for e in s["elements"] if e["role"]=="body" for line in e["lines"]),
                    baseline_regressions=baseline_checks,
                    baseline_lines_checked=sum(len(e["lines"]) for s in report["slides"] for e in s["elements"]),
                    baseline_words_checked=sum(len(line["words"]) for s in report["slides"] for e in s["elements"] for line in e["lines"]),
                    text_and_bounds_checks="Canonical body preserved; exact user display overrides recorded; all word origins use a common line baseline; every element inside canvas.")
    (reports/"carousel-validation.json").write_text(json.dumps(validation,indent=2)+"\n",encoding="utf-8")
    print(f'{len(report["slides"])} slides rendered; manifest and contact sheets in reports/nov16-29/')


if __name__=="__main__":
    main()
