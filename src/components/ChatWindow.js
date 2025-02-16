import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import { getAIMessage } from "../api/api";
import { marked } from "marked";
import robotIcon from "../assets/images/robot.png";
import userIcon from "../assets/images/user-icon.png";

function ChatWindow() {
  const defaultMessage = [{
    role: "assistant",
    content: "👋 Hi! I'm your PartSelect Assistant. We specialize in handling queries related to refrigerators and dishwashers. Which appliance do you need help with - refrigerator or dishwasher?"
  }];

  const [messages, setMessages] = useState(defaultMessage);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = (behavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Focus input on component mount
    inputRef.current?.focus();

    // Add scroll listener
    const container = messagesContainerRef.current;
    const handleScroll = () => {
      if (container) {
        const { scrollTop, scrollHeight, clientHeight } = container;
        setShowScrollButton(scrollHeight - scrollTop - clientHeight > 100);
      }
    };

    container?.addEventListener('scroll', handleScroll);
    return () => container?.removeEventListener('scroll', handleScroll);
  }, []);

  const simulateTyping = async (content) => {
    setIsTyping(true);
    // Add the message immediately but with a loading state
    setMessages(prevMessages => [...prevMessages, { role: "assistant", content: "", isLoading: true }]);
    
    // Calculate typing delay based on content length (faster for shorter messages)
    const baseDelay = 500;
    const charDelay = 0.1;
    const typingDelay = Math.min(baseDelay + content.length * charDelay, 2000);
    
    await new Promise(resolve => setTimeout(resolve, typingDelay));
    
    // Update the message with actual content
    setMessages(prevMessages => {
      const newMessages = [...prevMessages];
      newMessages[newMessages.length - 1] = { role: "assistant", content, isLoading: false };
      return newMessages;
    });
    setIsTyping(false);
  };

  const handleSend = async (inputText) => {
    if (inputText.trim() !== "") {
      setIsLoading(true);
      const userMessage = { role: "user", content: inputText };
      
      // Animate user message appearing
      setMessages(prevMessages => [...prevMessages, userMessage]);
      setInput("");
      inputRef.current?.focus();

      try {
        // Call API & set assistant message
        const newMessage = await getAIMessage(inputText);
        await simulateTyping(newMessage.content);
      } catch (error) {
        console.error('Error:', error);
        await simulateTyping("I apologize, but I encountered an error. Please try again.");
      } finally {
        setIsLoading(false);
      }
    }
  };

  const renderTypingIndicator = () => (
    <div className="typing-indicator">
      <span></span>
      <span></span>
      <span></span>
    </div>
  );

  const renderMessage = (message, index) => (
    <div 
      key={index} 
      className={`${message.role}-message-container animate-in`}
      style={{
        '--delay': `${index * 0.1}s`,
        animationDelay: `${index * 0.1}s`
      }}
    >
      {message.role === "assistant" && (
        <div className="assistant-avatar" title="PartSelect Assistant">
          <img src={robotIcon} alt="PartSelect Assistant" className="avatar-image" />
        </div>
      )}
      {message.role === "user" && (
        <div className="user-avatar" title="You">
          <img src={userIcon} alt="User" className="avatar-image" />
        </div>
      )}
      <div className={`message ${message.role}-message ${message.isLoading ? 'loading' : ''}`}>
        {message.isLoading ? (
          renderTypingIndicator()
        ) : (
          <div 
            className="message-content"
            dangerouslySetInnerHTML={{
              __html: marked(message.content).replace(/<p>|<\/p>/g, "")
            }} 
          />
        )}
      </div>
    </div>
  );

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h1>PartSelect Assistant</h1>
        <p>Find the right parts for your appliance</p>
      </div>
      
      <div className="messages-container" ref={messagesContainerRef}>
        {messages.map((message, index) => renderMessage(message, index))}
        <div ref={messagesEndRef} />
        
        {showScrollButton && (
          <button 
            className="scroll-to-bottom"
            onClick={() => scrollToBottom("smooth")}
            title="Scroll to bottom"
          >
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7 13L12 18L17 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M7 7L12 12L17 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        )}
      </div>

      <div className="input-area">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about parts, troubleshooting, or maintenance..."
          onKeyPress={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              handleSend(input);
              e.preventDefault();
            }
          }}
          disabled={isLoading}
        />
        <button 
          className={`send-button ${isLoading ? 'loading' : ''}`} 
          onClick={() => handleSend(input)}
          disabled={isLoading || input.trim() === ""}
          title="Send message"
        >
          {isLoading ? (
            <div className="button-loader"></div>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

export default ChatWindow;
