import React from "react";
import CustomTooltip from "../CustomTooltip/CustomTooltip";
import "./Sidebar.css";

const assetBaseUrl = import.meta.env.BASE_URL;

const Sidebar = ({
  isOpen,
  toggleSidebar,
  chatbots,
  selectedChatbot,
  onSelectChatbot,
  showDenodoSidebarHeaderIcon = true,
}) => {
  const globalBot = chatbots.find((bot) => bot.isGlobal);
  const specializedBots = chatbots.filter((bot) => !bot.isGlobal);

  const iconContainerStyle = {
    width: "32px",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    marginRight: "0.75rem",
    flexShrink: 0,
  };

  return (
    <div className={`sidebar-container ${isOpen ? "open" : "closed"}`}>
      <div
        className={`sidebar-header d-flex align-items-center px-3 ${
          showDenodoSidebarHeaderIcon ? "justify-content-between" : "justify-content-end"
        }`}
        style={{
          height: "76px",
          minHeight: "76px",
          backgroundColor: "#143142",
          borderRight: "2px solid #143b5c",
        }}
      >
        {showDenodoSidebarHeaderIcon && (
          <img
            src={`${assetBaseUrl}denodo_icon_white.svg`}
            alt="Denodo Logo"
            style={{ height: "30px", objectFit: "contain" }}
            onError={(e) => (e.target.style.display = "none")}
          />
        )}

        <i
          className="bi bi-arrow-bar-left text-white"
          onClick={toggleSidebar}
          style={{
            fontSize: "1.5rem",
            cursor: "pointer",
            transition: "opacity 0.2s",
          }}
          onMouseEnter={(e) => (e.target.style.opacity = "0.7")}
          onMouseLeave={(e) => (e.target.style.opacity = "1")}
          title="Close sidebar"
        ></i>
      </div>

      <div
        className="sidebar-content flex-grow-1 py-3 d-flex flex-column gap-3"
        style={{
          backgroundColor: "#f4f6f8",
          borderRight: "2px solid #e1e5e8",
        }}
      >
        {globalBot && (
          <div className="px-2">
            <CustomTooltip
              id="tooltip-global"
              content={
                globalBot.description ||
                "A general assistant ready to answer any questions."
              }
            >
              <div
                className={`sidebar-item d-flex align-items-center p-2 cursor-pointer ${selectedChatbot?.id === globalBot.id ? "active" : ""}`}
                onClick={() => onSelectChatbot(globalBot)}
              >
                <div style={iconContainerStyle}>
                  <img
                    src={`${assetBaseUrl}denodo_chat_transparent.png`}
                    alt=""
                    style={{
                      width: "30px",
                      height: "30px",
                      objectFit: "contain",
                    }}
                    onError={(e) => {
                      e.target.style.display = "none";
                      e.target.nextSibling.style.display = "inline-block";
                    }}
                  />
                  <i
                    className="bi bi-chat-left-text"
                    style={{ fontSize: "1.4rem", display: "none" }}
                  ></i>
                </div>
                <span className="text-truncate fw-medium" style={{ flexGrow: 1, textAlign: 'left' }}>Chat</span>
              </div>
            </CustomTooltip>
          </div>
        )}

        {globalBot && specializedBots.length > 0 && (
          <div
            className="mx-3"
            style={{ height: "2px", backgroundColor: "#e1e5e8" }}
          ></div>
        )}

        {specializedBots.length > 0 && (
          <div className="px-2 flex-grow-1 d-flex flex-column">
            <div
              className="d-flex align-items-center mb-2 px-2 text-muted"
              style={{
                fontSize: "0.75rem",
                fontWeight: 700,
                letterSpacing: "0.5px",
              }}
            >
              <span>AGENTS</span>

              <CustomTooltip
                id="tooltip-agents-info"
                content="Specialized assistants focused on handling specific tasks and data domains."
                delay={{ show: 200, hide: 300 }}
              >
                <i
                  className="bi bi-info-circle ms-2"
                  style={{
                    cursor: "help",
                    fontSize: "0.85rem",
                    color: "#adb5bd",
                    transition: "color 0.2s",
                  }}
                  onMouseEnter={(e) => (e.target.style.color = "#112533")}
                  onMouseLeave={(e) => (e.target.style.color = "#adb5bd")}
                ></i>
              </CustomTooltip>
            </div>

            <div className="d-flex flex-column gap-1">
              {specializedBots.map((bot) => (
                <CustomTooltip
                  key={bot.id}
                  id={`tooltip-${bot.id}`}
                  content={
                    <div className="text-start">
                      <strong style={{ fontSize: '1.05em', display: 'block', marginBottom: '4px' }}>
                        {bot.name}
                      </strong>
                      {bot.description && (
                        <span style={{ fontSize: '0.9em', opacity: 0.9 }}>
                          {bot.description}
                        </span>
                      )}
                    </div>
                  }
                >
                  <div
                    className={`sidebar-item d-flex align-items-center p-2 cursor-pointer ${selectedChatbot?.id === bot.id ? "active" : ""}`}
                    onClick={() => onSelectChatbot(bot)}
                  >
                    <div style={iconContainerStyle}>
                      {bot.icon ? (
                        <img
                          src={bot.icon}
                          alt=""
                          style={{
                            width: "30px",
                            height: "30px",
                            objectFit: "contain",
                          }}
                          onError={(e) => {
                            e.target.style.display = "none";
                            e.target.nextSibling.style.display = "inline-block";
                          }}
                        />
                      ) : null}
                      <i
                        className="bi bi-robot"
                        style={{
                          fontSize: "1.4rem",
                          display: bot.icon ? "none" : "inline-block",
                        }}
                      ></i>
                    </div>
                    <span className="text-truncate" style={{ flexGrow: 1, textAlign: 'left' }}>{bot.name}</span>
                  </div>
                </CustomTooltip>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
