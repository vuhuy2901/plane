export const getWorkflowErrorMessage = (error: unknown): string => {
  if (typeof error !== "object" || error === null || !("response" in error)) return "Request failed. Please try again.";
  const response = error.response;
  if (typeof response !== "object" || response === null || !("data" in response))
    return "Request failed. Please try again.";
  const data = response.data;
  if (typeof data !== "object" || data === null) return "Request failed. Please try again.";
  for (const value of Object.values(data)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    if (typeof value === "object" && value !== null && "message" in value) {
      const message = value.message;
      if (typeof message === "string") return message;
    }
  }
  return "Request failed. Please try again.";
};
