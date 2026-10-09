import { Fragment, ReactNode } from "react";
import { safeSource } from "@stock-scanner/client";

function inline(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g)
    .map((part, i) => {
      if (part.startsWith("**"))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
      const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link && safeSource(link[2]))
        return (
          <a
            key={i}
            href={safeSource(link[2])!}
            target="_blank"
            rel="noreferrer"
          >
            {link[1]} ↗
          </a>
        );
      return <Fragment key={i}>{part}</Fragment>;
    });
}

/** A small text-only renderer. Source HTML and scripts are never interpreted. */
export default function Markdown({
  text,
  sourceLabels = {},
}: {
  text: string;
  sourceLabels?: Record<string, string>;
}) {
  // Present authorized source references as dated report names. Downloads retain the original text.
  let displayed = text.replace(
    /\[inputs\.json\]\(\/work\/inputs\.json\)/g,
    "the selected evidence",
  );
  for (const [id, label] of Object.entries(sourceLabels))
    displayed = displayed.replaceAll(`\`${id}\``, label);
  const lines = displayed.split("\n"),
    blocks: ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      blocks.push(<h3 key={i}>{inline(heading[2])}</h3>);
      continue;
    }
    if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] ?? "")) {
      const cells = (s: string) =>
        s
          .replace(/^\s*\||\|\s*$/g, "")
          .split("|")
          .map((c) => c.trim());
      const headers = cells(line),
        rows: string[][] = [];
      const key = i;
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim())
        rows.push(cells(lines[i++]));
      i--;
      blocks.push(
        <div className="table-scroll" key={key}>
          <table>
            <thead>
              <tr>
                {headers.map((h, n) => (
                  <th key={n}>{inline(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, n) => (
                <tr key={n}>
                  {r.map((c, k) => (
                    <td key={k}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*(?:[-*]|\d+[.)])\s+/.test(line)) {
      const items: string[] = [],
        key = i,
        ordered = /^\s*\d+[.)]\s+/.test(line),
        pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/;
      while (i < lines.length && pattern.test(lines[i]))
        items.push(lines[i++].replace(pattern, ""));
      i--;
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={key} start={ordered ? parseInt(line.trim(), 10) : undefined}>
          {items.map((s, n) => (
            <li key={n}>{inline(s)}</li>
          ))}
        </List>,
      );
      continue;
    }
    blocks.push(<p key={i}>{inline(line)}</p>);
  }
  return <div className="readable-report">{blocks}</div>;
}
