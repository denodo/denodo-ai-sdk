import React, { useRef, useState, useEffect } from "react";
import CustomTooltip from "../CustomTooltip/CustomTooltip";
import Dropdown from "react-bootstrap/Dropdown";
import Spinner from "react-bootstrap/Spinner";
import "./Sidebar.css";

const assetBaseUrl = import.meta.env.BASE_URL;

const Sidebar = ({
  isOpen,
  toggleSidebar,
  chatbots,
  selectedChatbot,
  onSelectChatbot,
  showDenodoSidebarHeaderIcon = true,
  onNewChat,
  chatHistoryList = [],
  currentThreadId,
  onLoadOldChat,
  onDeleteChat,
  onRenameChat,
  onExportChat,
  onImportChat,
  onLoadMoreChats,
  hasMoreChats,
  isLoadingList,
  isLoadingHistory,
  onPinChat,
  searchQuery,
  onSearchChange,
  onOpenSettings,
}) => {
  const specializedBots = chatbots.filter((bot) => !bot.isGlobal);
  const fileInputRef = useRef(null);

  const [openDropdownId, setOpenDropdownId] = useState(null);
  const [isAgentsCollapsed, setIsAgentsCollapsed] = useState(false);
  const [isChatsCollapsed, setIsChatsCollapsed] = useState(false);

  useEffect(() => {
    const handleClickOutside = () => setOpenDropdownId(null);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      onImportChat(e.target.files[0]);
      e.target.value = null;
    }
  };

  return (
    <div className={`sidebar-container ${isOpen ? "open" : "closed"}`}>
      <div
        className={`sidebar-header d-flex align-items-center px-3 ${
          showDenodoSidebarHeaderIcon
            ? "justify-content-between"
            : "justify-content-end"
        }`}
      >
        {showDenodoSidebarHeaderIcon && (
          <img
            src={`${assetBaseUrl}denodo_icon_white.svg`}
            alt="Denodo Logo"
            className="sidebar-header-logo"
            onError={(e) => (e.target.style.display = "none")}
          />
        )}

        <i
          className="bi bi-arrow-bar-left sidebar-close-btn"
          onClick={toggleSidebar}
          title="Close sidebar"
        ></i>
      </div>

      <div className="sidebar-content flex-grow-1 py-3 d-flex flex-column gap-3">
        <div className="px-2 d-flex flex-column">
          <div
            className="sidebar-item new-chat-btn d-flex align-items-center p-2 cursor-pointer"
            onClick={onNewChat}
          >
            <div className="sidebar-icon-container">
              <i className="bi bi-pencil-square new-chat-icon"></i>
            </div>
            <span className="sidebar-item-text new-chat-text text-truncate">
              New chat
            </span>
          </div>
        </div>

        {specializedBots.length > 0 && (
          <>
            <div className="mx-3 sidebar-divider"></div>

            <div className="px-2 d-flex flex-column">
              <div
                className="sidebar-section-header px-3 cursor-pointer"
                onClick={() => setIsAgentsCollapsed(!isAgentsCollapsed)}
              >
                <div className="d-flex align-items-center">
                  <i
                    className={`bi bi-chevron-${
                      isAgentsCollapsed ? "right" : "down"
                    } me-2`}
                  ></i>
                  <span>AGENTS</span>
                </div>

                <div
                  className="info-icon-wrapper px-2"
                  onClick={(e) => e.stopPropagation()}
                >
                  <CustomTooltip
                    id="tooltip-agents-info"
                    content="Specialized agents focused on specific tasks and domains."
                    delay={{ show: 200, hide: 300 }}
                  >
                    <i className="bi bi-info-circle info-icon"></i>
                  </CustomTooltip>
                </div>
              </div>

              {!isAgentsCollapsed && (
                <div className="d-flex flex-column gap-1 mt-1">
                  {specializedBots.map((bot) => {
                    const isAgentDropdownOpen =
                      openDropdownId === `agent-${bot.id}`;

                    return (
                      <div
                        key={bot.id}
                        className={`sidebar-item d-flex align-items-center p-2 cursor-pointer ${
                          selectedChatbot?.id === bot.id ? "active" : ""
                        } ${isAgentDropdownOpen ? "dropdown-open" : ""}`}
                        onClick={() => onSelectChatbot(bot)}
                      >
                        <CustomTooltip
                          id={`tooltip-${bot.id}`}
                          disabled={isAgentDropdownOpen}
                          content={
                            <div className="text-start">
                              <strong>{bot.name}</strong>
                              <br />
                              {bot.description}
                            </div>
                          }
                        >
                          <div className="d-flex align-items-center flex-grow-1 overflow-hidden pe-4">
                            <div className="sidebar-icon-container">
                              {bot.icon ? (
                                <img
                                  src={bot.icon}
                                  alt=""
                                  className="agent-icon"
                                  onError={(e) => {
                                    e.target.style.display = "none";
                                    e.target.nextSibling.style.display =
                                      "inline-block";
                                  }}
                                />
                              ) : null}
                              <i
                                className="bi bi-robot agent-icon-fallback"
                                style={{
                                  display: bot.icon ? "none" : "inline-block",
                                }}
                              ></i>
                            </div>
                            <span className="sidebar-item-text text-truncate">
                              {bot.name}
                            </span>
                          </div>
                        </CustomTooltip>

                        <div className="sidebar-item-actions">
                          <div
                            className="sidebar-dots-menu"
                            onClick={(e) => {
                              e.stopPropagation();
                              setOpenDropdownId(
                                isAgentDropdownOpen ? null : `agent-${bot.id}`,
                              );
                            }}
                          >
                            <Dropdown show={isAgentDropdownOpen} drop="end">
                              <Dropdown.Toggle
                                as="div"
                                bsPrefix="dropdown-toggle-custom"
                                className="text-muted d-flex align-items-center"
                              >
                                <i className="bi bi-three-dots-vertical dropdown-dots-icon"></i>
                              </Dropdown.Toggle>

                              <Dropdown.Menu
                                className="shadow-lg border sidebar-dropdown-menu"
                                renderOnMount
                                popperConfig={{
                                  strategy: "fixed",
                                  modifiers: [
                                    {
                                      name: "preventOverflow",
                                      options: { boundary: "window" },
                                    },
                                    {
                                      name: "computeStyles",
                                      options: { adaptive: false },
                                    },
                                  ],
                                }}
                              >
                                <Dropdown.Item
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOpenDropdownId(null);
                                    if (onOpenSettings) onOpenSettings(bot);
                                  }}
                                >
                                  <i className="bi bi-gear-fill me-2"></i>{" "}
                                  Settings
                                </Dropdown.Item>
                              </Dropdown.Menu>
                            </Dropdown>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}

        <div className="mx-3 sidebar-divider"></div>

        <div className="px-2 d-flex flex-column">
          <div
            className="sidebar-section-header px-3 cursor-pointer"
            onClick={() => setIsChatsCollapsed(!isChatsCollapsed)}
          >
            <div className="d-flex align-items-center">
              <i
                className={`bi bi-chevron-${
                  isChatsCollapsed ? "right" : "down"
                } me-2`}
              ></i>
              <span>RECENT CHATS</span>
            </div>

            <div
              className="upload-icon-wrapper px-2 d-flex align-items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                style={{ display: "none" }}
                accept=".json"
                disabled={isLoadingHistory}
              />
              {isLoadingHistory ? (
                <Spinner
                  animation="border"
                  size="sm"
                  className="text-muted"
                  title="Importing..."
                />
              ) : (
                <i
                  className="bi bi-upload cursor-pointer upload-icon"
                  title="Import Chat"
                  onClick={() => fileInputRef.current.click()}
                ></i>
              )}
            </div>
          </div>

          {!isChatsCollapsed && (
            <>
              <div className="sidebar-search-wrapper">
                <div className="d-flex align-items-center border rounded sidebar-search-container">
                  <i className="bi bi-search text-muted me-2"></i>
                  <input
                    type="text"
                    placeholder="Search chats by title..."
                    className="form-control border-0 shadow-none bg-transparent p-0"
                    value={searchQuery}
                    onChange={(e) => onSearchChange(e.target.value)}
                  />
                  {searchQuery && (
                    <i
                      className="bi bi-x-circle-fill text-muted cursor-pointer ms-1 search-clear-icon"
                      onClick={() => onSearchChange("")}
                    ></i>
                  )}
                </div>
              </div>

              <div className="d-flex flex-column gap-1">
                {isLoadingList && chatHistoryList.length === 0 ? (
                  <div className="d-flex align-items-center gap-2 px-4 py-2 text-muted sidebar-status-message">
                    <Spinner animation="border" size="sm" />
                    <span>Loading...</span>
                  </div>
                ) : chatHistoryList.length === 0 ? (
                  <div className="px-4 text-muted text-center sidebar-status-message sidebar-empty-state">
                    {searchQuery
                      ? "No matching chats found."
                      : "No recent chats found."}
                  </div>
                ) : (
                  <>
                    {chatHistoryList.map((chat) => {
                      const isDropdownOpen = openDropdownId === chat.thread_id;

                      return (
                        <div
                          key={chat.thread_id}
                          className={`sidebar-item d-flex align-items-center p-2 cursor-pointer ${
                            currentThreadId === chat.thread_id ? "active" : ""
                          } ${isDropdownOpen ? "dropdown-open" : ""}`}
                          onClick={() => onLoadOldChat(chat)}
                          title={chat.title}
                        >
                          <span className="sidebar-item-text text-truncate pe-4">
                            {chat.title}
                          </span>

                          <div className="sidebar-item-actions">
                            {chat.is_pinned && (
                              <i className="bi bi-pin-fill sidebar-pin-icon"></i>
                            )}

                            <div
                              className="sidebar-dots-menu"
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenDropdownId(
                                  isDropdownOpen ? null : chat.thread_id,
                                );
                              }}
                            >
                              <Dropdown show={isDropdownOpen} drop="end">
                                <Dropdown.Toggle
                                  as="div"
                                  bsPrefix="dropdown-toggle-custom"
                                  className="text-muted d-flex align-items-center"
                                >
                                  <i className="bi bi-three-dots-vertical dropdown-dots-icon"></i>
                                </Dropdown.Toggle>

                                <Dropdown.Menu
                                  className="shadow-lg border sidebar-dropdown-menu"
                                  renderOnMount
                                  popperConfig={{
                                    strategy: "fixed",
                                    modifiers: [
                                      {
                                        name: "preventOverflow",
                                        options: { boundary: "window" },
                                      },
                                      {
                                        name: "computeStyles",
                                        options: { adaptive: false },
                                      },
                                    ],
                                  }}
                                >
                                  <Dropdown.Item
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setOpenDropdownId(null);
                                      onPinChat(
                                        chat.thread_id,
                                        !chat.is_pinned,
                                      );
                                    }}
                                  >
                                    <i
                                      className={`bi ${
                                        chat.is_pinned
                                          ? "bi-pin"
                                          : "bi-pin-fill"
                                      } me-2`}
                                    ></i>
                                    {chat.is_pinned ? "Unpin chat" : "Pin chat"}
                                  </Dropdown.Item>

                                  <Dropdown.Item
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setOpenDropdownId(null);
                                      onRenameChat(chat);
                                    }}
                                  >
                                    <i className="bi bi-pencil-fill me-2"></i>{" "}
                                    Rename
                                  </Dropdown.Item>

                                  <Dropdown.Item
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setOpenDropdownId(null);
                                      onExportChat(chat);
                                    }}
                                  >
                                    <i className="bi bi-download me-2"></i>{" "}
                                    Export
                                  </Dropdown.Item>

                                  <Dropdown.Divider />

                                  <Dropdown.Item
                                    className="text-danger"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setOpenDropdownId(null);
                                      onDeleteChat(chat.thread_id);
                                    }}
                                  >
                                    <i className="bi bi-trash3 me-2"></i> Delete
                                  </Dropdown.Item>
                                </Dropdown.Menu>
                              </Dropdown>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    {hasMoreChats && !searchQuery && (
                      <div
                        className="text-center py-3 mt-1 cursor-pointer sidebar-load-more"
                        onClick={onLoadMoreChats}
                      >
                        <i className="bi bi-chevron-down me-1"></i> Load older
                        chats
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
