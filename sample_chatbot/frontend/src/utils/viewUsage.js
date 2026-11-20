// Shared logic for deciding which searched views an answer actually used.
//
// The candidate views come from the AI SDK artifact `tables_used` (the views
// returned by the vector search). A view counts as used when the generated
// VQL references it as "db"."view" (see isViewUsedInVql).

export const cleanViewName = (name) => String(name || "").replace(/"/g, "").trim();

const normalizeViewName = (name) => cleanViewName(name).toLowerCase();

// A view is used when the VQL references it as "db"."view". Checking the
// quoted form (with a bare db.view fallback on word boundaries) avoids
// prefix false positives such as `loan` matching inside `loan_officer`.
function isViewUsedInVql(normalizedTable, rawVql, cleanVql) {
  const quoted = normalizedTable
    .split(".")
    .map((part) => `"${part}"`)
    .join(".");
  if (rawVql.includes(quoted)) return true;
  const escaped = normalizedTable.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9_])${escaped}([^a-z0-9_]|$)`).test(cleanVql);
}

export function splitUsedTables(tables, vql, extraViews) {
  let rawVql = "";
  if (Array.isArray(vql)) {
    rawVql = vql.filter(Boolean).map((entry) => String(entry).toLowerCase()).join(" ");
  } else if (vql) {
    rawVql = String(vql).toLowerCase();
  }
  const cleanVql = rawVql.replace(/"/g, "");

  // extraViews: views already known (e.g. in the context window) that were
  // not searched for this answer. The agent may reuse their schemas without
  // a new metadata_search, so they can still be the used ones. They only
  // ever join the used side; the unused side stays the searched views.
  const usedTables = [];
  const seenUsed = new Set();
  const markUsed = (table) => {
    const key = normalizeViewName(table);
    if (key && !seenUsed.has(key)) {
      seenUsed.add(key);
      usedTables.push(table);
    }
  };

  const unusedTables = [];
  (tables || []).forEach((table) => {
    if (!normalizeViewName(table)) return;
    if (isViewUsedInVql(normalizeViewName(table), rawVql, cleanVql)) {
      markUsed(table);
    } else {
      unusedTables.push(table);
    }
  });
  (extraViews || []).forEach((view) => {
    const name = typeof view === "string" ? view : view && view.name;
    if (name && isViewUsedInVql(normalizeViewName(name), rawVql, cleanVql)) {
      markUsed(name);
    }
  });
  return { usedTables, unusedTables };
}

// Map of normalized view name -> token count, built from the live context
// window usage views. Views from older answers may no longer be in context,
// in which case they simply have no token count to show.
export function buildViewTokenLookup(contextViews) {
  const lookup = new Map();
  for (const view of contextViews || []) {
    if (view && view.name != null && view.tokens) {
      lookup.set(normalizeViewName(view.name), view.tokens);
    }
  }
  return lookup;
}

export function viewTokens(table, lookup) {
  if (!lookup) return null;
  const tokens = lookup.get(normalizeViewName(table));
  return tokens == null ? null : tokens;
}
