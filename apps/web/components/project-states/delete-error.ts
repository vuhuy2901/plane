type StateDeleteErrorResponse = {
  status?: number;
  data?: {
    code?: string;
    message?: string;
    error?: string;
  };
};

export const getStateDeleteErrorMessage = (error: unknown) => {
  const response = error as StateDeleteErrorResponse;
  if (response.status === 400) {
    return (
      response.data?.message ??
      response.data?.error ??
      "This state cannot be deleted until its work items or workflow references are removed."
    );
  }
  return "State could not be deleted. Please try again.";
};
