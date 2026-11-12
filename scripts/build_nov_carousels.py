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
        "description": "User-requested heading and three separate numbered items, using uniform 84px type with hanging indents on wrapped continuation lines; 80/76/72px fallback only if needed to fit.",
        "kind": "line_breaks",
    },
    ("N06", 4): {
        "display_text": "Par total byaaj:\nPersonal loan ₹13,77,250\nLAP ₹31,37,623\nKam EMI ka matlab sasta loan nahi.",
        "description": "User-requested heading, two separate loan/interest items, and closing paragraph, using uniform 84px type with 80/76/72px fallback only if needed; remove the middot only here.",
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
            words.append(dict(text=token,bounds=[round(v/SCALE,2) for v in ink],fill=color,
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
        kinds=["heading","numbered_item","numbered_item","numbered_item"] if item["id"]=="N02" else ["heading","total_item","total_item","closing"]
        policy=dict(safe_box=[MARGIN,250,W-MARGIN,1120],font_steps=[84,80,76,72],
                    line_height_factor=1.18,group_gap=36,weight="Extrabold",valign="center",
                    numeric_fill=LIME,hanging_indent="number prefix including its trailing space")
        x1,y1,x2,y2=policy["safe_box"]
        plan=None
        for size in policy["font_steps"]:
            leading=round(size*policy["line_height_factor"])
            baseline=font(size,"Extrabold").getmetrics()[0]/SCALE
            candidate=[]
            groups=[]
            fits=True
            for index,(text,kind) in enumerate(zip(texts,kinds)):
                if index:
                    baseline+=policy["group_gap"]
                match=re.match(r"^(\d+\.\s+)(.*)$",text) if kind=="numbered_item" else None
                prefix=match[1] if match else ""
                content=match[2] if match else text
                text_start=round((x1+self.width(prefix,size,"Extrabold"))*SCALE)/SCALE
                remaining=content.split()
                paragraph_lines=[]
                while remaining:
                    continuation=bool(paragraph_lines)
                    origin_x=text_start if continuation else x1
                    visible_prefix="" if continuation else prefix
                    words=[]
                    while remaining:
                        proposed=visible_prefix+" ".join(words+[remaining[0]])
                        if self.width(proposed,size,"Extrabold")>x2-origin_x:
                            break
                        words.append(remaining.pop(0))
                    if not words:
                        fits=False
                        break
                    paragraph_lines.append(dict(text=visible_prefix+" ".join(words),x=origin_x,
                                                baseline=baseline,paragraph_index=index,group_role=kind,
                                                is_continuation=continuation))
                    baseline+=leading
                if not fits:
                    break
                indices=list(range(len(candidate),len(candidate)+len(paragraph_lines)))
                groups.append(dict(index=index,text=text,kind=kind,prefix=prefix,first_line_x=x1,
                                   text_start_x=text_start,continuation_x=text_start,line_indices=indices))
                candidate.extend(paragraph_lines)
            if not fits:
                continue
            boxes=[self.ink_bounds(line["text"],line["x"],line["baseline"],size,"Extrabold") for line in candidate]
            top=min(box[1] for box in boxes)
            bottom=max(box[3] for box in boxes)
            if bottom-top<=y2-y1 and all(x1<=box[0] and box[2]<=x2 for box in boxes):
                plan=(size,leading,candidate,groups,top,bottom)
                break
        if plan is None:
            raise ValueError(f'{item["id"]}/{slide["number"]:02d} does not fit the safe area at 84, 80, 76 or 72px; refusing smaller type.')
        size,leading,planned_lines,groups,top,bottom=plan
        offset=y1+(y2-y1-(bottom-top))/2-top
        records=[]
        for planned in planned_lines:
            record=self.draw_baseline_line(planned["text"],planned["x"],planned["baseline"]+offset,size,"Extrabold",accent_numbers=True)
            record.update(paragraph_index=planned["paragraph_index"],group_role=planned["group_role"],is_continuation=planned["is_continuation"])
            records.append(record)
        for group in groups:
            boxes=[records[index]["bounds"] for index in group["line_indices"]]
            group["bounds"]=[min(box[0] for box in boxes),min(box[1] for box in boxes),max(box[2] for box in boxes),max(box[3] for box in boxes)]
        assert all(line["font_size"]==size>=72 for line in records)
        assert normalized(" ".join(line["text"] for line in records))==normalized(spec["display_text"])
        assert all(y1<=line["bounds"][1] and line["bounds"][3]<=y2 for line in records)
        override=dict(requested_by_user=True,kind=spec["kind"],canonical_text=slide["text"],
                      display_text=spec["display_text"],description=spec["description"])
        self.record_element("body",slide["text"],records,size,"Extrabold",spec["display_text"],override)
        self.elements[-1].update(groups=groups,layout_policy=dict(policy,selected_font_size=size,leading=leading,ink_height=bottom-top))

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


def select_slide_keys(items, selectors=None, only=None):
    """Resolve an explicit render scope without writing any image or report."""
    ordered=[(item["id"],slide["number"]) for item in items for slide in item["slides"]]
    valid=set(ordered)
    ids={item["id"] for item in items}
    if selectors:
        selected=set()
        for selector in selectors:
            match=re.fullmatch(r"(N\d{2})/(\d{2})",selector)
            if not match:
                raise ValueError(f"Bad slide selector {selector!r}; use N02/04.")
            key=(match[1],int(match[2]))
            if key not in valid:
                raise ValueError(f"Unknown carousel slide: {selector}")
            selected.add(key)
    elif only:
        unknown=set(only)-ids
        if unknown:
            raise ValueError(f"Unknown carousel item(s): {', '.join(sorted(unknown))}")
        selected={key for key in ordered if key[0] in only}
    else:
        selected=valid
    return [key for key in ordered if key in selected]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument("--only",nargs="*",help="Render every slide in the named carousel IDs; retain the other manifest rows.")
    selection.add_argument("--slide",action="append",help="Render only this ID/slide, e.g. N02/04. Repeat to select multiple slides.")
    parser.add_argument("--self-test",action="store_true",help="Run the mixed-glyph and negative baseline regressions only.")
    args=parser.parse_args()
    baseline_checks=baseline_regressions()
    if args.self_test:
        print(json.dumps(baseline_checks,indent=2))
        return
    data=json.loads((ROOT/"batch_nov16_29/batch.json").read_text(encoding="utf-8"))
    assert not data.get("series_pending"),"Exact series tags must be resolved before rendering."
    items=[i for i in data["items"] if i["type"]=="carousel"]
    all_keys=[(item["id"],slide["number"]) for item in items for slide in item["slides"]]
    try:
        selected_keys=set(select_slide_keys(items,args.slide,args.only))
    except ValueError as exc:
        parser.error(str(exc))
    reports=ROOT/"reports/nov16-29"
    manifest_path=reports/"carousel-render-manifest.json"
    rows={}
    if selected_keys!=set(all_keys):
        if not manifest_path.is_file():
            parser.error("Selective rendering needs the existing complete carousel manifest; render the full batch first.")
        prior=json.loads(manifest_path.read_text(encoding="utf-8"))
        prior_rows={(row["id"],row["slide"]):row for row in prior["slides"]}
        for key in all_keys:
            if key in selected_keys:
                continue
            expected=f"media/{key[0]}/{key[1]:02d}.jpg"
            row=prior_rows.get(key)
            if row is None or row.get("path")!=expected or not (ROOT/expected).is_file():
                parser.error(f"Selective rendering needs the existing manifest row and JPEG for {key[0]}/{key[1]:02d}.")
            rows[key]=row
    report=dict(canvas=[W,H],color_space="sRGB",jpeg_quality=95,supersampling=SCALE,
                text_anchor="ls",origin_units="final-image pixels; pixel_origin is the 2x raster coordinate",
                baseline_regressions=baseline_checks,
                updated_media=[f"media/{item_id}/{number:02d}.jpg" for item_id,number in all_keys if (item_id,number) in selected_keys],slides=[])
    for item in items:
        for slide in item["slides"]:
            key=(item["id"],slide["number"])
            if key not in selected_keys:
                continue
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
            rows[key]=row
            print(f'rendered {row["path"]} ({row["main_body_words"]} body words)')
    report["slides"]=[rows[key] for key in all_keys]
    assert len(report["slides"])==len(all_keys),"A selective render must retain the complete batch manifest."
    reports.mkdir(parents=True,exist_ok=True)
    manifest_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    contact_sheet(report["slides"],reports/"carousel-all-slides.jpg")
    contact_sheet([s for s in report["slides"] if s["slide"]==1],reports/"carousel-covers.jpg",columns=3,thumb_width=320)
    validation=dict(status="passed",rendered_images=len(report["slides"]),updated_images=len(selected_keys),
                    updated_media=report["updated_media"],canvas=[W,H],jpeg_quality=95,
                    icc="embedded sRGB",max_file_bytes=max(s["bytes"] for s in report["slides"]),
                    total_bytes=sum(s["bytes"] for s in report["slides"]),
                    max_main_body_words=max(s["main_body_words"] for s in report["slides"]),
                    minimum_main_body_font_size=min(line["font_size"] for s in report["slides"] for e in s["elements"] if e["role"]=="body" for line in e["lines"]),
                    baseline_regressions=baseline_checks,
                    baseline_lines_checked=sum(len(e["lines"]) for s in report["slides"] for e in s["elements"]),
                    baseline_words_checked=sum(len(line["words"]) for s in report["slides"] for e in s["elements"] for line in e["lines"]),
                    text_and_bounds_checks="Canonical body preserved; exact user display overrides recorded; all word origins use a common line baseline; every element inside canvas.")
    (reports/"carousel-validation.json").write_text(json.dumps(validation,indent=2)+"\n",encoding="utf-8")
    print(f'{len(selected_keys)} JPEGs updated; complete {len(report["slides"])}-slide manifest and contact sheets in reports/nov16-29/')


if __name__=="__main__":
    main()
