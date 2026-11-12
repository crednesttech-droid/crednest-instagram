#!/usr/bin/env python3
"""Render the six exact-copy Nov 16–29 carousels; never edits the queue.

The approved brief and subsequent user clarifications live in batch_nov16_29/.
All text is loaded from that manifest. Geometry is rendered at 2x then exported
as a 1080x1350 quality-95 JPEG with an embedded sRGB ICC profile.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path
import re

from PIL import Image, ImageCms, ImageDraw, ImageFont

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

    def ink_bounds(self, line, x, y, size, weight):
        box=self.draw.textbbox((round(x*SCALE),round(y*SCALE)),line,font=font(size,weight),anchor="lt")
        return [round(v/SCALE,2) for v in box]

    def fit(self, text, box, max_size, min_size, weight="Extrabold", spacing=1.14):
        x1,y1,x2,y2=box
        for size in range(max_size,min_size-1,-1):
            lines=self.wrap(text,size,x2-x1,weight)
            if not lines:
                continue
            leading=round(size*spacing)
            bounds=[self.ink_bounds(line,x1,y1+n*leading,size,weight) for n,line in enumerate(lines)]
            if max(b[3] for b in bounds)<=y2:
                return size,lines,leading
        raise ValueError(f"Copy does not fit at {min_size}px: {text}")

    def block(self, role, text, box, max_size, min_size, weight="Extrabold", spacing=1.14,
              fill=None, valign="top", accent_numbers=False):
        size,lines,leading=self.fit(text,box,max_size,min_size,weight,spacing)
        x,y,x2,y2=box
        last=self.ink_bounds(lines[-1],x,y+(len(lines)-1)*leading,size,weight)
        if valign=="center":
            y+=(y2-last[3])/2
        records=[]
        for n,line in enumerate(lines):
            ly=y+n*leading
            if accent_numbers and self.theme=="dark":
                # Drawing individual tokens does not alter their text or sequence.
                xpos=x
                for token in re.findall(r"\S+\s*",line):
                    token_fill=self.colors["accent"] if re.search(r"\d|₹",token) else (fill or self.colors["fg"])
                    self.draw.text((round(xpos*SCALE),round(ly*SCALE)),token,font=font(size,weight),fill=token_fill,anchor="lt")
                    xpos+=self.width(token,size,weight)
            else:
                self.draw.text((round(x*SCALE),round(ly*SCALE)),line,font=font(size,weight),fill=fill or self.colors["fg"],anchor="lt")
            records.append(dict(text=line,bounds=self.ink_bounds(line,x,ly,size,weight)))
        bounds=[min(b["bounds"][0] for b in records),min(b["bounds"][1] for b in records),
                max(b["bounds"][2] for b in records),max(b["bounds"][3] for b in records)]
        assert all(0<=bounds[i]<=(W if i%2==0 else H) for i in range(4)), (role,bounds)
        self.elements.append(dict(role=role,text=text,bounds=bounds,font_size=size,weight=weight,lines=records))
        return bounds

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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only",nargs="*",help="Render only the named carousel IDs.")
    args=parser.parse_args()
    data=json.loads((ROOT/"batch_nov16_29/batch.json").read_text(encoding="utf-8"))
    assert not data.get("series_pending"),"Exact series tags must be resolved before rendering."
    report=dict(canvas=[W,H],color_space="sRGB",jpeg_quality=95,supersampling=SCALE,slides=[])
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
            report["slides"].append(row)
            print(f'rendered {row["path"]} ({row["main_body_words"]} body words)')
    reports=ROOT/"reports/nov16-29"
    reports.mkdir(parents=True,exist_ok=True)
    (reports/"carousel-render-manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    contact_sheet(report["slides"],reports/"carousel-all-slides.jpg")
    contact_sheet([s for s in report["slides"] if s["slide"]==1],reports/"carousel-covers.jpg",columns=3,thumb_width=320)
    print(f'{len(report["slides"])} slides rendered; manifest and contact sheets in reports/nov16-29/')


if __name__=="__main__":
    main()
