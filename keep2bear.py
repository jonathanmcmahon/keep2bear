import argparse
import json
import pathlib
import shutil

from datetime import datetime
from uuid import uuid4


TB_EXT = "textbundle"  # bearnote
TB_CONTENT_FILE = "text.txt"
TB_METADATA_FILE = "info.json"
TB_ASSET_DIR = "assets"


class ConversionError(Exception):
    pass


def get_args():
    parser = argparse.ArgumentParser(
        description="convert exported Google Keep notes to Bear"
    )

    parser.add_argument("-i", "--input", required=True, help="Google Takeout directory")
    parser.add_argument("-o", "--out", required=True, help="Output directory")
    parser.add_argument(
        "--ignorecolors",
        action="store_true",
        default=False,
        help="Do not convert Google Keep colors to Bear tags",
    )

    args = parser.parse_args()
    return args


def datetime_to_str(ts):
    return ts.astimezone().replace(microsecond=0).isoformat()


def now():
    return datetime_to_str(datetime.now())


def new_tbundle_meta(created_ts, mod_ts, pinned, archived, trashed):
    tbundle = {
        "net.shinyfrog.bear": {
            "pinned": int(pinned),
            "trashedDate": mod_ts if trashed else None,
            "archived": int(archived),
            "modificationDate": mod_ts,
            "creationDate": created_ts,
            "pinnedDate": mod_ts if pinned else None,
            "trashed": int(trashed),
            "uniqueIdentifier": str(uuid4()),
            "archivedDate": mod_ts if archived else None,
            "lastEditingDevice": "keep2bear",
        },
        "transient": True,
        "type": "public.plain-text",
        "creatorIdentifier": "net.shinyfrog.bear",
        "version": 2,
    }
    return tbundle


def convert_metadata(note, created_ts):

    # Convert time from POSIX ns timestamp
    mod_ts = datetime.fromtimestamp(int(note["userEditedTimestampUsec"]) / 10e5)
    mod_ts = datetime_to_str(mod_ts)

    meta = new_tbundle_meta(
        created_ts=created_ts,
        mod_ts=mod_ts,
        pinned=note["isPinned"],
        archived=note["isArchived"],
        trashed=note["isTrashed"],
    )

    return meta


def convert_list(_list):
    mdlist = []
    for item in _list:
        check_status = "+" if item["isChecked"] else "-"
        mdlist.append(" ".join([check_status, item["text"]]))
    return "\n".join(mdlist)


def ann_convert_weblink(ann):
    templ = "[{title}]({url})\n> {description}"
    return templ.format(
        title=ann["title"], url=ann["url"], description=ann["description"]
    )


def convert_note_annotations(note):
    # Map Google Keep annotation source types to conversion functions
    converters = {
        "WEBLINK": ann_convert_weblink,
    }

    annotations = []
    if "annotations" in note:
        # Results in single newline between content and annotations due to join()
        annotations.append("")
        for ann in note["annotations"]:
            if ann["source"] not in converters:
                raise ConversionError("Unknown annotation type: '%s'" % ann["source"])
            conversion_fn = converters[ann["source"]]
            annotations.append(conversion_fn(ann))
    return "\n".join(annotations)


def convert_note_text(note, ignore_colors):

    text = []

    if "textContent" in note:
        content = note["textContent"]
    elif "listContent" in note:
        content = convert_list(note["listContent"])

    if note["title"]:
        title = note["title"]
        text.append("# {}".format(title))
    else:
        # Otherwise, title is simply first line of content
        # We use title for naming textbundle directory
        title = content.split("\n")[0]

    text.append(content)

    text.append(convert_note_annotations(note))

    color = note["color"]
    if (color != "DEFAULT") and not ignore_colors:
        text.append("#{}".format(color))

    return title, text


def convert_note_attachments(note, srcpath):
    assets, embeds = [], []
    if "attachments" in note:
        for att in note["attachments"]:
            fname = att["filePath"]
            src_file = srcpath / fname
            if not src_file.is_file():
                raise ConversionError(
                    "could not find file '%s' referenced by note '%s'"
                    % (src_file, note)
                )
            assets.append(src_file)
            # Embed this file at end of note text
            embeds.append("[{}/{}]".format(TB_ASSET_DIR, fname))
    return assets, embeds


def write_textbundle(title, text, meta, assets, outdir):
    # Create note directory
    tb_title = "".join(c for c in title if (c.isalnum() or c in "._- "))
    tb_title = tb_title[:50]
    tb_title = "{}.{}".format(tb_title, TB_EXT)
    tb_dir = outdir / tb_title
    if tb_dir.exists():
        tb_title += str(uuid4())[:8]
        tb_dir = outdir / tb_title
    tb_dir.mkdir(exist_ok=False)

    # Copy note assets
    if assets:
        asset_dir = tb_dir / TB_ASSET_DIR
        asset_dir.mkdir(exist_ok=False)
        for src_file in assets:
            dst_file = asset_dir / src_file.name
            shutil.copy(str(src_file), str(dst_file))

    # Write note metadata
    with open(str(tb_dir / TB_METADATA_FILE), "w") as f:
        f.write(json.dumps(meta))

    # Write note text
    with open(str(tb_dir / TB_CONTENT_FILE), "w") as f:
        f.write("\n".join(text))


def process_note(note, created_ts, srcpath, outdir, ignore_colors):

    # Convert metadata, note text, and note attachments
    meta = convert_metadata(note, created_ts)
    title, text = convert_note_text(note, ignore_colors)
    assets, embeds = convert_note_attachments(note, srcpath)

    # Append attachments to end of note
    text += embeds

    # Write convert textbundle
    write_textbundle(title, text, meta, assets, outdir)


def main(args):

    # Create timestamped directory for conversion output
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = pathlib.Path(args.out) / "keep2bear_{}".format(run_ts)
    outdir.mkdir(exist_ok=False)
    print("Saving output to %s" % outdir)

    srcpath = pathlib.Path(args.input) / "Keep"
    assert srcpath.is_dir(), "Could not find 'Keep' directory in '%s'" % args.input

    # Locate input files to convert
    print("Finding Google Keep files...")
    keepnotes = list(srcpath.glob("*.json"))
    print("Found %s Google Keep notes." % len(keepnotes))

    # Convert each note
    for idx, keepnote in enumerate(keepnotes):
        print("Processing %s / %s..." % (idx + 1, len(keepnotes)))
        created_ts = datetime.fromtimestamp(keepnote.stat().st_mtime)
        created_ts = datetime_to_str(created_ts)
        with open(str(keepnote)) as f:
            note = json.loads(f.read())
            process_note(note, created_ts, srcpath, outdir, args.ignorecolors)

    print("\n\nConversion complete.\n")


if __name__ == "__main__":
    main(get_args())
