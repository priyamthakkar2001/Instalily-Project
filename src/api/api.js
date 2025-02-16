export const getAIMessage = async (userQuery) => {
  try {
    const response = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        userQuery: userQuery,
        context: {} // We can add context later if needed
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return {
      role: data.role,
      content: data.content
    };
  } catch (error) {
    console.error('Error:', error);
    return {
      role: "assistant",
      content: "Sorry, I encountered an error while processing your request. Please try again."
    };
  }
};
