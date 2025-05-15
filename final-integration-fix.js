// Replace the existing virtual session code in createSession with this implementation

// For virtual sessions, create a Google Meet link
if (sessionType === "virtual") {
  try {
    // Make a POST request to create a Google Meet with all necessary information
    const meetResponse = await fetch("https://vidyasangam.duckdns.org/api/utility/create-meet", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("authToken")}`
      },
      body: JSON.stringify({
        summary: summary || "Mentoring Session",
        description: "Scheduled mentoring session via Vidyasangam",
        start_time: scheduledDateTime.toISOString(),
        end_time: new Date(scheduledDateTime.getTime() + 60*60000).toISOString(), // 1 hour session
        timezone: "Asia/Kolkata",
        attendees: participantRegNos.map(regNo => ({ email: `${regNo}@example.com` }))
      }),
      credentials: "include" // Critical for sending cookies with the request
    });
    
    // If the response is not JSON, it might be a redirect
    const contentType = meetResponse.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      if (meetResponse.redirected) {
        // Open the redirect URL in a popup window
        const authWindow = window.open(meetResponse.url, "Google Authorization", "width=800,height=600");
        alert("Please complete the Google authorization in the popup window, then try creating the session again.");
        setIsLoading(false);
        return;
      }
      throw new Error("Unexpected response format");
    }
    
    const meetData = await meetResponse.json();
    
    // Check if we need authorization (backend will return auth URL if needed)
    if (meetData.authorization_url) {
      // Open the Google auth URL in a popup window
      const authWindow = window.open(meetData.authorization_url, "Google Authorization", "width=800,height=600");
      
      // Create a promise that resolves when the popup closes
      const authPromise = new Promise((resolve) => {
        const checkClosed = setInterval(() => {
          if (authWindow.closed) {
            clearInterval(checkClosed);
            resolve();
          }
        }, 500);
      });
      
      // Wait for auth to complete
      await authPromise;
      
      // Let the user know to try again
      alert("Please try creating the session again now that you've authorized with Google.");
      setIsLoading(false);
      return;
    }
    
    // If we have a meeting link, use it
    if (meetData.meet_link) {
      meetingLink = meetData.meet_link;
    } else {
      console.error("Meet creation response:", meetData);
      throw new Error("Failed to create Google Meet link");
    }
  } catch (error) {
    console.error("Error creating Google Meet:", error);
    alert("Failed to create Google Meet link. Please try again.");
    setIsLoading(false);
    return;
  }
} else {
  // For physical session
  if (!sessionLocation) {
    sessionLocation = "To be determined";
  }
} 