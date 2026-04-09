import React, { useState, useRef, useEffect } from "react";
import { Overlay, Tooltip } from "react-bootstrap";
import "./CustomTooltip.css";

const CustomTooltip = ({
  id,
  content,
  children,
  delay = { show: 400, hide: 250 },
  placement = "right",
}) => {
  const [show, setShow] = useState(false);
  const target = useRef(null);

  const showTimeout = useRef(null);
  const hideTimeout = useRef(null);

  useEffect(() => {
    return () => {
      clearTimeout(showTimeout.current);
      clearTimeout(hideTimeout.current);
    };
  }, []);

  const handleMouseEnter = () => {
    clearTimeout(hideTimeout.current);

    if (!show) {
      showTimeout.current = setTimeout(() => {
        setShow(true);
      }, delay.show);
    }
  };

  const handleMouseLeave = () => {
    clearTimeout(showTimeout.current);

    hideTimeout.current = setTimeout(() => {
      setShow(false);
    }, delay.hide);
  };

  return (
    <>
      {React.cloneElement(children, {
        ref: target,
        onMouseEnter: handleMouseEnter,
        onMouseLeave: handleMouseLeave,
      })}

      <Overlay target={target.current} show={show} placement={placement}>
        {(props) => (
          <Tooltip
            id={id}
            {...props}
            className="custom-light-tooltip"
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          >
            <div className="custom-tooltip-scroll-content">{content}</div>
          </Tooltip>
        )}
      </Overlay>
    </>
  );
};

export default CustomTooltip;
