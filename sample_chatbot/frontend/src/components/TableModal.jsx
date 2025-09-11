import React, { useState, useMemo } from 'react';
import Modal from 'react-bootstrap/Modal';
import Table from 'react-bootstrap/Table';
import Pagination from 'react-bootstrap/Pagination';

const TableModal = ({ show, llm_response_rows_limit, handleClose, executionResult }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 10;

  const tableData = useMemo(() => {
    if (!executionResult || typeof executionResult === 'string' || Object.keys(executionResult).length === 0) {
      return { headers: [], rows: [] };
    }
    
    const rows = Object.values(executionResult);
    if (rows.length === 0 || !Array.isArray(rows[0])) {
      return { headers: [], rows: [] };
    }
    
    const headers = rows[0].map(item => item.columnName);
    const dataRows = rows.map(row => 
      row.map(item => item.value)
    );

    return { headers, rows: dataRows };
  }, [executionResult]);

  const totalRows = tableData.rows.length;
  const totalPages = Math.ceil(totalRows / rowsPerPage);
  
  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * rowsPerPage;
    const endIndex = Math.min(startIndex + rowsPerPage, totalRows);
    return tableData.rows.slice(startIndex, endIndex);
  }, [tableData.rows, currentPage, rowsPerPage, totalRows]);

  const handlePageChange = (pageNumber) => {
    setCurrentPage(pageNumber);
  };

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const items = [];
    const maxPageItems = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxPageItems / 2));
    let endPage = Math.min(totalPages, startPage + maxPageItems - 1);

    if (endPage - startPage + 1 < maxPageItems) {
      startPage = Math.max(1, endPage - maxPageItems + 1);
    }

    // Previous button
    items.push(
      <Pagination.Prev 
        key="prev" 
        onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
      />
    );

    // First page
    if (startPage > 1) {
      items.push(
        <Pagination.Item key={1} onClick={() => handlePageChange(1)}>
          1
        </Pagination.Item>
      );
      if (startPage > 2) {
        items.push(<Pagination.Ellipsis key="ellipsis-1" disabled />);
      }
    }

    // Page numbers
    for (let page = startPage; page <= endPage; page++) {
      items.push(
        <Pagination.Item 
          key={page} 
          active={page === currentPage}
          onClick={() => handlePageChange(page)}
        >
          {page}
        </Pagination.Item>
      );
    }

    // Last page
    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        items.push(<Pagination.Ellipsis key="ellipsis-2" disabled />);
      }
      items.push(
        <Pagination.Item key={totalPages} onClick={() => handlePageChange(totalPages)}>
          {totalPages}
        </Pagination.Item>
      );
    }

    // Next button
    items.push(
      <Pagination.Next 
        key="next" 
        onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
        disabled={currentPage === totalPages}
      />
    );

    return (
      <div className="d-flex justify-content-center mt-3">
        <Pagination>{items}</Pagination>
      </div>
    );
  };

  return (
    <Modal 
      show={show} 
      onHide={handleClose} 
      size="lg" 
      centered
      style={{ '--bs-modal-bg': '#112533' }}
      contentClassName="text-white border border-white"
    >
      <Modal.Header closeButton className="border-bottom border-white">
        <Modal.Title>Execution Result</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {totalRows > 0 ? (
          <>
            <div className="alert alert-info mb-3">
              To avoid sending too many tokens to the LLM, it only has access to
              the first {llm_response_rows_limit} rows. You can view the
              complete execution result from Denodo here.
            </div>
            <div className="table-responsive">
              <Table className="custom-table" striped bordered hover variant="dark">
                <thead>
                  <tr>
                    {tableData.headers.map((header, index) => (
                      <th key={index}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedRows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex}>{String(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            {renderPagination()}
            <div className="mt-3 text-center text-white">
              Showing rows {(currentPage - 1) * rowsPerPage + 1}-{Math.min(currentPage * rowsPerPage, totalRows)} of {totalRows}
            </div>
          </>
        ) : (
          <div className="text-center py-4">No data available</div>
        )}
      </Modal.Body>
    </Modal>
  );
};

export default TableModal; 