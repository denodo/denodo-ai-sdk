/**
 * Builds the Data Marketplace link for a view returned by the AI SDK.
 */
export const buildViewCatalogUrl = (dataCatalogUrl, table) => {
  if (!dataCatalogUrl || !table) {
    return null;
  }

  const cleanTable = String(table).replace(/"/g, "");
  const separatorIndex = cleanTable.indexOf(".");
  const database =
    separatorIndex === -1 ? cleanTable : cleanTable.slice(0, separatorIndex);
  const viewName =
    separatorIndex === -1 ? cleanTable : cleanTable.slice(separatorIndex + 1);

  return `${dataCatalogUrl}/#/view/${database}/${viewName}`;
};

export default buildViewCatalogUrl;
