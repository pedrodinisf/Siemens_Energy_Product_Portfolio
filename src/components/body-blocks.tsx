import type { ReactNode } from "react";
import type { BodyBlock } from "@/lib/catalog";

function renderRich(text: string, bold?: string[]): ReactNode {
  const phrases = (bold ?? []).filter(Boolean).sort((a, b) => b.length - a.length);
  if (!phrases.length) return text;
  const nodes: ReactNode[] = [];
  let rest = text;
  let key = 0;
  while (rest) {
    let bestIndex = -1;
    let bestPhrase = "";
    for (const phrase of phrases) {
      const index = rest.toLowerCase().indexOf(phrase.toLowerCase());
      if (index !== -1 && (bestIndex === -1 || index < bestIndex)) {
        bestIndex = index;
        bestPhrase = phrase;
      }
    }
    if (bestIndex === -1) {
      nodes.push(rest);
      break;
    }
    if (bestIndex > 0) nodes.push(rest.slice(0, bestIndex));
    nodes.push(
      <strong key={key++} className="font-semibold text-fg">
        {rest.slice(bestIndex, bestIndex + bestPhrase.length)}
      </strong>,
    );
    rest = rest.slice(bestIndex + bestPhrase.length);
  }
  return nodes;
}

const headingClass: Record<2 | 3 | 4, string> = {
  2: "pt-4 font-display text-xl font-semibold text-fg first:pt-0",
  3: "pt-3 font-display text-lg font-semibold text-fg",
  4: "pt-2 font-semibold text-fg",
};

/** Renders a cleaned item body; `max` previews the first N blocks. */
export function BodyBlocks({ blocks, max }: { blocks?: BodyBlock[]; max?: number }) {
  if (!blocks?.length) return null;
  const shown = max ? blocks.slice(0, max) : blocks;
  let previousLevel = 1;
  const rendered = shown.map((block) => {
    if (block.type !== "heading") return block;
    // Keep the document outline from skipping levels (axe heading-order).
    const level = Math.min(block.level, previousLevel + 1) as 2 | 3 | 4;
    previousLevel = level;
    return { ...block, level };
  });
  return (
    <div className="max-w-[68ch] space-y-4 text-base leading-[1.7] text-body">
      {rendered.map((block, i) => {
        if (block.type === "heading") {
          const Tag = `h${block.level}` as "h2" | "h3" | "h4";
          return (
            <Tag key={i} className={headingClass[block.level]}>
              {block.text}
            </Tag>
          );
        }
        if (block.type === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag
              key={i}
              className={`${block.ordered ? "list-decimal" : "list-disc"} space-y-1.5 pl-5 marker:text-subtle`}
            >
              {block.items.map((item, j) => (
                <li key={j}>{item}</li>
              ))}
            </Tag>
          );
        }
        return <p key={i}>{renderRich(block.text, block.bold)}</p>;
      })}
    </div>
  );
}
