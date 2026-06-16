#!/usr/bin/env python3
"""
generate_mermaid.py - Generate Mermaid diagrams from LIA-SEC code analysis

Commands:
  flowchart <title> <nodes_json>   Generate flowchart from nodes
  sequence <title> <actors_json>   Generate sequence diagram
  erd <title> <entities_json>      Generate ERD from entities
  class <title> <classes_json>     Generate class diagram
  from-go <go_file>                Extract and generate from Go file
  from-tsx <tsx_file>              Extract and generate from TSX file

Output: .mmd file + .json source in _alire/01_DOCUMENTATION/diagrams/
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

DIAGRAM_DIR = "_alire/01_DOCUMENTATION/diagrams"


def ensure_dir():
    os.makedirs(DIAGRAM_DIR, exist_ok=True)


def save_diagram(name: str, mmd_content: str, source_data: dict):
    """Save .mmd and .json source files."""
    ensure_dir()
    mmd_path = os.path.join(DIAGRAM_DIR, f"{name}.mmd")
    json_path = os.path.join(DIAGRAM_DIR, f"{name}.json")

    with open(mmd_path, "w") as f:
        f.write(mmd_content)

    source_data["generated"] = date.today().isoformat()
    source_data["generator"] = "generate_mermaid.py"
    with open(json_path, "w") as f:
        json.dump(source_data, f, indent=2)

    print(f"Generated: {mmd_path}")
    print(f"Source:    {json_path}")
    return mmd_path


def cmd_flowchart(args):
    if len(args) < 2:
        print("Usage: generate_mermaid.py flowchart <name> <nodes_json_file>")
        sys.exit(1)

    name = args[0]
    with open(args[1]) as f:
        data = json.load(f)

    lines = [f"flowchart {data.get('direction', 'TD')}"]
    for node in data.get("nodes", []):
        nid = node["id"]
        label = node.get("label", nid)
        shape = node.get("shape", "rect")
        if shape == "round":
            lines.append(f"    {nid}({label})")
        elif shape == "diamond":
            lines.append(f"    {nid}{{{{{label}}}}}")
        elif shape == "cylinder":
            lines.append(f"    {nid}[({label})]")
        else:
            lines.append(f"    {nid}[{label}]")

    for edge in data.get("edges", []):
        src, dst = edge["from"], edge["to"]
        label = edge.get("label", "")
        if label:
            lines.append(f"    {src} -->|{label}| {dst}")
        else:
            lines.append(f"    {src} --> {dst}")

    for style in data.get("styles", []):
        lines.append(f"    style {style['id']} {style['css']}")

    mmd = "\n".join(lines) + "\n"
    save_diagram(name, mmd, {"type": "flowchart", "input": data})


def cmd_sequence(args):
    if len(args) < 2:
        print("Usage: generate_mermaid.py sequence <name> <actors_json_file>")
        sys.exit(1)

    name = args[0]
    with open(args[1]) as f:
        data = json.load(f)

    lines = ["sequenceDiagram"]
    for actor in data.get("actors", []):
        lines.append(f"    participant {actor['id']} as {actor.get('label', actor['id'])}")

    for msg in data.get("messages", []):
        arrow = "->>" if msg.get("async") else "->>"
        if msg.get("response"):
            arrow = "-->>"
        lines.append(f"    {msg['from']}{arrow}{msg['to']}: {msg['text']}")
        if msg.get("note"):
            lines.append(f"    Note over {msg['from']},{msg['to']}: {msg['note']}")

    mmd = "\n".join(lines) + "\n"
    save_diagram(name, mmd, {"type": "sequence", "input": data})


def cmd_erd(args):
    if len(args) < 2:
        print("Usage: generate_mermaid.py erd <name> <entities_json_file>")
        sys.exit(1)

    name = args[0]
    with open(args[1]) as f:
        data = json.load(f)

    lines = ["erDiagram"]
    for entity in data.get("entities", []):
        ename = entity["name"]
        lines.append(f"    {ename} {{")
        for field in entity.get("fields", []):
            ftype = field.get("type", "string")
            fname = field["name"]
            pk = "PK" if field.get("pk") else ""
            fk = "FK" if field.get("fk") else ""
            constraint = pk or fk
            lines.append(f"        {ftype} {fname} {constraint}".rstrip())
        lines.append("    }")

    for rel in data.get("relations", []):
        cardinality = rel.get("cardinality", "||--o{")
        lines.append(f'    {rel["from"]} {cardinality} {rel["to"]} : "{rel.get("label", "")}"')

    mmd = "\n".join(lines) + "\n"
    save_diagram(name, mmd, {"type": "erd", "input": data})


def cmd_from_go(args):
    """Extract structs and handlers from a Go file, generate class diagram."""
    if not args:
        print("Usage: generate_mermaid.py from-go <go_file>")
        sys.exit(1)

    filepath = args[0]
    with open(filepath) as f:
        content = f.read()

    name = Path(filepath).stem

    # Extract structs
    structs = re.findall(r'type (\w+) struct \{([^}]+)\}', content, re.MULTILINE)
    # Extract func signatures
    funcs = re.findall(r'func (\w+)\(([^)]*)\)', content)

    lines = ["classDiagram"]
    for struct_name, fields in structs:
        lines.append(f"    class {struct_name} {{")
        for field_line in fields.strip().split("\n"):
            field_line = field_line.strip()
            if field_line and not field_line.startswith("//"):
                parts = field_line.split()
                if len(parts) >= 2:
                    lines.append(f"        +{parts[1]} {parts[0]}")
        lines.append("    }")

    handler_funcs = [f[0] for f in funcs if f[0].startswith("handle")]
    if handler_funcs:
        lines.append(f"    class Handlers {{")
        for h in handler_funcs[:20]:
            lines.append(f"        +{h}()")
        lines.append("    }")

    mmd = "\n".join(lines) + "\n"
    save_diagram(name, mmd, {"type": "class", "source_file": filepath, "structs": len(structs), "handlers": len(handler_funcs)})


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "flowchart": cmd_flowchart,
        "sequence": cmd_sequence,
        "erd": cmd_erd,
        "from-go": cmd_from_go,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
