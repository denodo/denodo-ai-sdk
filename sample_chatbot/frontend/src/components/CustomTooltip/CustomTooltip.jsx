import React, { useState, useRef, useEffect } from "react";
import { Overlay, Tooltip } from "react-bootstrap";
import "./CustomTooltip.css";

const CustomTooltip = ({
  id,
  content,
  children,
  delay = { show: 400, hide: 250 },
  placement = "right",
  disabled = false,
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

  useEffect(() => {
    if (disabled) {
      clearTimeout(showTimeout.current);
      setShow(false);
    }
  }, [disabled]);

  useEffect(() => {
    const currentTarget = target.current;
    if (!currentTarget) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          clearTimeout(showTimeout.current);
          setShow(false);
        }
      },
      {
        root: null,
        threshold: 0,
      }
    );

    observer.observe(currentTarget);

    return () => {
      observer.disconnect();
    };
  }, []);

  const handleMouseEnter = () => {
    if (disabled) return;
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

  const handleClick = (e) => {
    clearTimeout(showTimeout.current);
    setShow(false);
    if (children.props.onClick) {
      children.props.onClick(e);
    }
  };

  return (
    <>
      {React.cloneElement(children, {
        ref: target,
        onMouseEnter: handleMouseEnter,
        onMouseLeave: handleMouseLeave,
        onClick: handleClick,
      })}

      <Overlay
        target={target.current}
        show={show && !disabled}
        placement={placement}
      >
        {(props) => (
          <Tooltip
            id={id}
            {...props}
            className="custom-light-tooltip"
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            style={{ ...props.style, pointerEvents: "none" }}
          >
            <div className="custom-tooltip-scroll-content">{content}</div>
          </Tooltip>
        )}
      </Overlay>
    </>
  );
};

export default CustomTooltip;
