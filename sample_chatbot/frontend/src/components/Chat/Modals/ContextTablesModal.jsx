import React, { useMemo } from "react";
import { BaseModal } from "../../Common/Modal";
import { ViewChip } from "../../QuestionForm/ContextViewsRow";
import {
  splitUsedTables,
  buildViewTokenLookup,
  viewTokens,
  cleanViewName,
} from "../../../utils/viewUsage";

const ContextTablesModal = ({ show, onClose, onExited, tables, vql, dataCatalogUrl, contextViews }) => {
  const { usedTables, unusedTables } = useMemo(
    () => splitUsedTables(tables, vql, contextViews),
    [tables, vql, contextViews],
  );
  const tokenLookup = useMemo(
    () => buildViewTokenLookup(contextViews),
    [contextViews],
  );

  const renderChips = (list, used) => (
    <div className="d-flex flex-wrap" style={{ gap: "8px" }}>
      {list.map((table) => (
        <ViewChip
          key={table}
          view={{ name: cleanViewName(table), tokens: viewTokens(table, tokenLookup) }}
          dataCatalogUrl={dataCatalogUrl}
          showHint={false}
          used={used}
        />
      ))}
    </div>
  );

  return (
    <BaseModal
      show={show}
      onHide={onClose}
      onExited={onExited}
      title="Context Tables"
      size="lg"
      scrollableBody
      footer={null}
    >
      <>
        {usedTables.length > 0 && (
          <div className="mb-4">
            <h6 className="mb-3">
              <strong>Used in Query ({usedTables.length})</strong>
            </h6>
            {renderChips(usedTables, true)}
          </div>
        )}

        {unusedTables.length > 0 && (
          <div className="mb-3">
            <h6 className="mb-3">
              <strong>
                Searched but Not Used ({unusedTables.length})
              </strong>
            </h6>
            {renderChips(unusedTables, false)}
          </div>
        )}

        <div className="mt-4 pt-3 border-top border-secondary">
          <small>
            <strong>Note:</strong> Views in green were used to find the answer,
            while grey tables were found in the database but found not relevant
            to the question.
          </small>
        </div>
      </>
    </BaseModal>
  );
};

export default ContextTablesModal;
