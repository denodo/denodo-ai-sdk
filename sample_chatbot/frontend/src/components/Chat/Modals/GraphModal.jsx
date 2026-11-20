import React, { useEffect, useState } from "react";
import Tab from "react-bootstrap/Tab";
import Tabs from "react-bootstrap/Tabs";
import { BaseModal } from "../../Common/Modal";
import CopyButton from "../../CopyButton/CopyButton";
import { SqlBlock } from "./AdditionalInformationModal";

// Graph image without any modal wrapper, so it can also be shown inline
export const GraphView = ({ graph }) => (
  <div className="text-center">
    {graph && <img src={graph} alt="Graph" className="img-fluid" />}
  </div>
);

const VqlPanel = ({ vql }) => (
  <div>
    <div className="d-flex align-items-center justify-content-between mb-2">
      <span className="text-muted" style={{ fontSize: "0.85rem" }}>
        VQL query used to generate this graph
      </span>
      <span className="d-inline-flex align-items-center gap-1">
        <CopyButton text={String(vql)} tooltipText="Copy VQL" />
        <span style={{ fontSize: "0.85rem" }}>Copy VQL</span>
      </span>
    </div>
    <SqlBlock sql={String(vql)} />
  </div>
);

const GraphModal = ({ show, graph, vql, onClose, onExited }) => {
  const [segment, setSegment] = useState("graph");

  useEffect(() => {
    if (show) setSegment("graph");
  }, [show]);

  const hasVql = Boolean(vql && String(vql).trim());

  return (
    <BaseModal
      show={show}
      onHide={onClose}
      onExited={onExited}
      title="Graph View"
      size="lg"
      footer={null}
    >
      <Tabs activeKey={segment} onSelect={(key) => key && setSegment(key)}>
        <Tab eventKey="graph" title="Graph">
          <div className="modal-scroll-container">
            <GraphView graph={graph} />
          </div>
        </Tab>
        <Tab eventKey="vql" title="VQL">
          <div className="modal-scroll-container">
            {hasVql ? (
              <VqlPanel vql={vql} />
            ) : (
              <p className="text-muted mb-0">
                VQL not available for this graph. It may have been saved before the VQL was stored with the graph.
              </p>
            )}
          </div>
        </Tab>
      </Tabs>
    </BaseModal>
  );
};

export default GraphModal;
