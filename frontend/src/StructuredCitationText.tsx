import type { ReactNode } from "react";

type TableSegment = {
  kind: "table";
  rows: string[][];
  source: "markdown" | "tsv";
};
type TextSegment = { kind: "text"; text: string };
type Segment = TableSegment | TextSegment;

function endsWithUnescapedPipe(value: string): boolean {
  if (!value.endsWith("|")) return false;
  let escapes = 0;
  for (let index = value.length - 2; index >= 0 && value[index] === "\\"; index--)
    escapes++;
  return escapes % 2 === 0;
}

function splitMarkdownRow(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !endsWithUnescapedPipe(trimmed)) return null;

  const cells: string[] = [];
  let cell = "";
  for (let index = 1; index < trimmed.length - 1; index++) {
    const character = trimmed[index];
    let escapes = 0;
    for (let slash = index - 1; slash >= 0 && trimmed[slash] === "\\"; slash--)
      escapes++;
    if (character === "|" && escapes % 2 === 0) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function markdownTableAt(lines: string[], start: number): TableSegment | null {
  const headers = splitMarkdownRow(lines[start]);
  const separators = splitMarkdownRow(lines[start + 1] ?? "");
  if (
    !headers ||
    !separators ||
    headers.length < 2 ||
    headers.some((header) => !header) ||
    separators.length !== headers.length ||
    separators.some((cell) => !/^:?-{3,}:?$/.test(cell))
  )
    return null;

  const rows = [headers];
  let index = start + 2;
  while (index < lines.length) {
    const cells = splitMarkdownRow(lines[index]);
    if (!cells) break;
    if (cells.length !== headers.length) return null;
    rows.push(cells);
    index++;
  }
  return rows.length > 1 ? { kind: "table", rows, source: "markdown" } : null;
}

function tsvRow(line: string): string[] | null {
  if (!line.includes("\t")) return null;
  return line.split("\t");
}

function tsvTableAt(lines: string[], start: number): TableSegment | null {
  if (start > 0 && tsvRow(lines[start - 1])) return null;
  const rows: string[][] = [];
  let index = start;
  while (index < lines.length) {
    const line = lines[index];
    const cells = tsvRow(line);
    if (!cells) break;
    if (line.includes('"') || (rows.length > 0 && cells.length !== rows[0].length))
      return null;
    rows.push(cells);
    index++;
  }
  if (
    rows.length < 2 ||
    rows[0].length < 2 ||
    rows[0].some((header) => !header.trim())
  )
    return null;
  return { kind: "table", rows, source: "tsv" };
}

function parseStructuredText(text: string): Segment[] | null {
  const lines = text.split(/\r?\n/);
  const segments: Segment[] = [];
  let textStart = 0;
  let index = 0;

  while (index < lines.length - 1) {
    const markdown = markdownTableAt(lines, index);
    const markdownHeader = splitMarkdownRow(lines[index]);
    const markdownRule = splitMarkdownRow(lines[index + 1] ?? "");
    if (markdownHeader && markdownRule && !markdown) return null;
    const tsv = markdown ? null : tsvTableAt(lines, index);
    const table = markdown ?? tsv;
    if (!table) {
      // A malformed row immediately following a clear table makes the excerpt
      // ambiguous. Keep the complete original excerpt in its plain rendering.
      const markdownRow = splitMarkdownRow(lines[index]);
      const previous = segments.at(-1);
      if (
        markdownRow &&
        previous?.kind === "table" &&
        previous.source === "markdown"
      )
        return null;
      index++;
      continue;
    }

    if (index > textStart) {
      segments.push({ kind: "text", text: lines.slice(textStart, index).join("\n") });
    }
    segments.push(table);
    index += table.rows.length + (table.source === "markdown" ? 1 : 0);
    textStart = index;
  }

  if (!segments.some((segment) => segment.kind === "table")) return null;
  if (textStart < lines.length) {
    segments.push({ kind: "text", text: lines.slice(textStart).join("\n") });
  }
  return segments;
}

function StructuredTable({
  rows,
  label,
}: {
  rows: string[][];
  label: string;
}) {
  const [headers, ...body] = rows;
  return (
    <div
      className="citation-table-viewport"
      role="region"
      aria-label={`${label}（表は横にスクロールできます）`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault();
          event.currentTarget.scrollBy({
            left: event.key === "ArrowRight" ? 80 : -80,
          });
        }
      }}
    >
      <table aria-label={label}>
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th scope="col" key={index}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) =>
                cellIndex === 0 ? (
                  <th scope="row" key={cellIndex}>
                    {cell}
                  </th>
                ) : (
                  <td key={cellIndex}>{cell}</td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StructuredCitationText({
  text,
  label,
}: {
  text: string;
  label: string;
}) {
  const segments = parseStructuredText(text);
  if (!segments) return <blockquote>{text}</blockquote>;

  const content: ReactNode[] = segments.map((segment, index) =>
    segment.kind === "table" ? (
      <StructuredTable key={index} rows={segment.rows} label={label} />
    ) : (
      <div className="citation-text" key={index}>
        {segment.text}
      </div>
    ),
  );
  return <blockquote>{content}</blockquote>;
}
