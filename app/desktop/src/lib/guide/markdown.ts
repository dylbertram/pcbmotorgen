/**
 * markdown.ts — minimal markdown → HTML renderer for the in-app plugin
 * authoring guide (kata bprp).
 * ============================================================================
 *
 * The guide is bundled at build time from the routing crate docs
 * (`crates/pcbmotorgen-routing/docs/*.md` via Vite `?raw` imports — see
 * `docs.ts`). Those documents use a small, known markdown subset, so instead
 * of pulling in a full renderer dependency this module implements exactly
 * that subset with STRICT escaping:
 *
 *   - ATX headings (`#` .. `######`)
 *   - fenced code blocks (``` with an optional language tag)
 *   - GFM pipe tables (with `:---:` alignment columns and `\|` cell escapes)
 *   - blockquotes (recursively parsed)
 *   - ordered / unordered lists, GitHub task-list items (`- [ ]` / `- [x]`),
 *     with lazy continuation lines (wrapped item text)
 *   - thematic breaks (`---`, `***`)
 *   - paragraphs
 *   - inline: code spans, **bold**, *italic* / _italic_ (word-boundary
 *     guarded so snake_case outside code spans is never mangled),
 *     `[label](href)` links (labels may themselves contain code spans —
 *     the API.md intro uses `` [`file.md`](./file.md) ``)
 *
 * Safety model: ALL text is HTML-escaped and raw HTML in the source is
 * NEVER passed through, so the output is safe to inject with `{@html}`.
 * Only `http(s)` / `mailto` hrefs become real anchors — the docs' relative
 * repo links (e.g. `./routing-pattern-handoff.md`) render as inert code-styled
 * text, since they have no meaning inside the app.
 *
 * Known limitations (fine for this content): no setext headings, no nested
 * lists, no reference links, no images, no HTML pass-through.
 */

// ---------------------------------------------------------------------------
// Escaping
// ---------------------------------------------------------------------------

function escapeText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(text: string): string {
  return escapeText(text).replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Inline rendering
// ---------------------------------------------------------------------------

/** Emphasis with `_` must not start/end inside a word (snake_case safety). */
const EM_UNDERSCORE_RE = /(?<![\w\\])_(?=\S)([^_]*\S)_(?!\w)/g;
const EM_STAR_RE = /(^|[^*\\])\*(?=\S)([^*]*\S)\*/g;
const STRONG_RE = /\*\*(?=\S)([^*]*\S)\*\*/g;

const CODE_SPAN_RE = /`([^`\n]+)`/y;
const LINK_RE = /\[([^\]\n]*)\]\(([^)\s]+)\)/y;

/** Only these href schemes become real anchors; anything else renders inert. */
const SAFE_HREF_RE = /^(https?:\/\/|mailto:)/i;

/** Format (bold/italic) an already-escaped text run. */
function formatEscaped(escaped: string): string {
  let out = escaped;
  out = out.replace(STRONG_RE, "<strong>$1</strong>");
  out = out.replace(EM_UNDERSCORE_RE, "<em>$1</em>");
  out = out.replace(EM_STAR_RE, (_m, pre: string, inner: string) => `${pre}<em>${inner}</em>`);
  return out;
}

/**
 * Render the inline markdown subset of `text` to HTML.
 *
 * Single left-to-right scan: whichever inline token (code span or link)
 * starts earliest wins. That ordering makes `` [`f.md`](./f.md) `` a link
 * whose label renders its own code span, and `` `[x](y)` `` a pure code
 * span — both appear in the bundled docs.
 */
export function renderInline(text: string): string {
  let out = "";
  let plainStart = 0;
  let i = 0;

  const pushPlain = (end: number): void => {
    if (end > plainStart) {
      out += formatEscaped(escapeText(text.slice(plainStart, end)));
    }
  };

  while (i < text.length) {
    LINK_RE.lastIndex = i;
    const linkMatch = LINK_RE.exec(text);
    const linkHere = linkMatch !== null && linkMatch.index === i ? linkMatch : null;

    CODE_SPAN_RE.lastIndex = i;
    const codeMatch = CODE_SPAN_RE.exec(text);
    const codeHere = codeMatch !== null && codeMatch.index === i ? codeMatch : null;

    if (linkHere === null && codeHere === null) {
      i += 1; // plain character; the run is flushed at the next token
      continue;
    }

    pushPlain(i);
    if (linkHere !== null) {
      const href = linkHere[2];
      const label = linkHere[1];
      if (SAFE_HREF_RE.test(href)) {
        out +=
          `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">` +
          `${renderInline(label)}</a>`;
      } else {
        // Relative repo link (e.g. `./routing-pattern-handoff.md`): inert.
        // Strip the label's code-span backticks for a clean path display.
        const bare = label.replace(/^`([\s\S]*)`$/, "$1");
        out += `<code class="md-link-ref">${escapeText(bare)}</code>`;
      }
      i += linkHere[0].length;
    } else if (codeHere !== null) {
      out += `<code>${escapeText(codeHere[1])}</code>`;
      i += codeHere[0].length;
    }
    plainStart = i;
  }

  pushPlain(text.length);
  return out;
}

// ---------------------------------------------------------------------------
// Block rendering
// ---------------------------------------------------------------------------

const FENCE_OPEN_RE = /^\s{0,3}```\s*([\w+-]*)\s*$/;
const FENCE_CLOSE_RE = /^\s{0,3}```\s*$/;
const HEADING_RE = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR_RE = /^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/;
const BLOCKQUOTE_RE = /^\s{0,3}>/;
const UL_ITEM_RE = /^\s*[-*]\s+(.*)$/;
const OL_ITEM_RE = /^\s*\d{1,9}[.)]\s+(.*)$/;
const TASK_ITEM_RE = /^\[([ xX])\]\s+(.*)$/;
const TABLE_DELIM_CELL_RE = /^:?-{3,}:?$/;

function isBlank(line: string): boolean {
  return /^\s*$/.test(line);
}

function isListItem(line: string): boolean {
  return UL_ITEM_RE.test(line) || OL_ITEM_RE.test(line);
}

/** A line that must terminate an open paragraph when collecting one. */
function isBlockStart(line: string): boolean {
  return (
    isBlank(line) ||
    FENCE_OPEN_RE.test(line) ||
    HEADING_RE.test(line) ||
    HR_RE.test(line) ||
    BLOCKQUOTE_RE.test(line) ||
    isListItem(line) ||
    line.includes("|") // a pipe line may open a table — let the caller decide
  );
}

/** True when `line` is a GFM table delimiter row (`| --- | :---: | ...`). */
function isTableDelimiter(line: string): boolean {
  if (!line.includes("-") || !line.includes("|")) return false;
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((c) => TABLE_DELIM_CELL_RE.test(c));
}

/**
 * Split a table row into cells. `\|` is an escaped literal pipe (GFM) and
 * must not split the cell.
 */
function splitTableRow(line: string): string[] {
  const trimmed = line.trim();
  const body = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutTrailing =
    body.endsWith("|") && !body.endsWith("\\|") ? body.slice(0, -1) : body;
  return withoutTrailing
    .split(/(?<!\\)\|/)
    .map((cell) => cell.replace(/\\\|/g, "|").trim());
}

type ColumnAlign = "left" | "center" | "right" | null;

function parseAlignments(delimiterLine: string): ColumnAlign[] {
  return splitTableRow(delimiterLine).map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return null;
  });
}

function alignmentStyle(align: ColumnAlign): string {
  return align === null ? "" : ` style="text-align: ${align};"`;
}

/** Render one table; `lines[start]` is its header row. */
function renderTable(lines: string[], start: number): { html: string; next: number } {
  const alignments = parseAlignments(lines[start + 1]);
  const headerCells = splitTableRow(lines[start]);

  const thead = `<thead><tr>${headerCells
    .map((cell, i) => `<th${alignmentStyle(alignments[i] ?? null)}>${renderInline(cell)}</th>`)
    .join("")}</tr></thead>`;

  let i = start + 2;
  const rows: string[] = [];
  while (i < lines.length && lines[i].includes("|") && !isBlank(lines[i])) {
    const cells = splitTableRow(lines[i]);
    rows.push(
      `<tr>${cells
        .map((cell, c) => `<td${alignmentStyle(alignments[c] ?? null)}>${renderInline(cell)}</td>`)
        .join("")}</tr>`,
    );
    i += 1;
  }
  const tbody = `<tbody>${rows.join("")}</tbody>`;
  return { html: `<table>${thead}${tbody}</table>`, next: i };
}

/** Render an ordered/unordered list block starting at lines[start]. */
function renderList(lines: string[], start: number): { html: string; next: number } {
  const ordered = OL_ITEM_RE.test(lines[start]);
  const itemRe = ordered ? OL_ITEM_RE : UL_ITEM_RE;

  const items: string[] = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) break;
    const match = itemRe.exec(line);
    if (match) {
      items.push(match[1]);
      i += 1;
      continue;
    }
    if (isBlockStart(line)) break;
    if (items.length === 0) break;
    // Lazy continuation: wrapped text belonging to the previous item.
    items[items.length - 1] += ` ${line.trim()}`;
    i += 1;
  }

  const lis = items
    .map((raw) => {
      const task = TASK_ITEM_RE.exec(raw);
      if (task) {
        const checked = task[1].toLowerCase() === "x";
        return (
          `<li><input type="checkbox" disabled${checked ? " checked" : ""}> ` +
          `${renderInline(task[2])}</li>`
        );
      }
      return `<li>${renderInline(raw)}</li>`;
    })
    .join("");

  const html = ordered ? `<ol>${lis}</ol>` : `<ul>${lis}</ul>`;
  return { html, next: i };
}

/**
 * Render the markdown subset used by the routing crate docs to an HTML
 * string (safe for `{@html}` — everything is escaped, nothing passes
 * through raw).
 */
export function markdownToHtml(markdown: string): string {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (isBlank(line)) {
      i += 1;
      continue;
    }

    // Fenced code block.
    const fenceOpen = FENCE_OPEN_RE.exec(line);
    if (fenceOpen) {
      const lang = fenceOpen[1];
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE_CLOSE_RE.test(lines[i])) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1; // consume the closing fence (or run off the end)
      const langClass = /^[\w+-]+$/.test(lang) ? ` class="language-${escapeAttr(lang)}"` : "";
      out.push(`<pre><code${langClass}>${escapeText(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    // ATX heading.
    const heading = HEADING_RE.exec(line);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    // Thematic break.
    if (HR_RE.test(line)) {
      out.push("<hr>");
      i += 1;
      continue;
    }

    // Pipe table (needs a delimiter row on the next line).
    if (line.includes("|") && i + 1 < lines.length && isTableDelimiter(lines[i + 1])) {
      const table = renderTable(lines, i);
      out.push(table.html);
      i = table.next;
      continue;
    }

    // Blockquote (parsed recursively after stripping the markers).
    if (BLOCKQUOTE_RE.test(line)) {
      const inner: string[] = [];
      while (i < lines.length && BLOCKQUOTE_RE.test(lines[i]) && !isBlank(lines[i])) {
        inner.push(lines[i].replace(/^\s{0,3}>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote>${markdownToHtml(inner.join("\n"))}</blockquote>`);
      continue;
    }

    // Ordered / unordered list.
    if (isListItem(line)) {
      const list = renderList(lines, i);
      out.push(list.html);
      i = list.next;
      continue;
    }

    // Paragraph: collect plain continuation lines until a block starts.
    const para: string[] = [line.trim()];
    i += 1;
    while (i < lines.length && !isBlockStart(lines[i])) {
      para.push(lines[i].trim());
      i += 1;
    }
    out.push(`<p>${renderInline(para.join(" "))}</p>`);
  }

  return out.join("\n");
}
