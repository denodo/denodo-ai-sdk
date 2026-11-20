// Helpers to turn DeepQuery report HTML into downloadable files.

export const buildReportFilename = (title, fallback = "deepquery") => {
  const safeTitle = (title || "")
    .trim()
    .replace(/[/\\?%*:|"<>]/g, "")
    .replace(/\s+/g, "_");
  return `${safeTitle || fallback}_report.html`;
};

export const downloadHtmlFile = (html, title, fallback) => {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = buildReportFilename(title, fallback);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Revoke on the next tick so the browser has started the download
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
