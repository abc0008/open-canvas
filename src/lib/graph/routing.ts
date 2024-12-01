import { END } from "@langchain/langgraph";
import { GraphState, MessageWithToolCalls } from "./types";
import { GraphExecutionError } from "./error";

export function routeMessage(state: typeof GraphState.State) {
  try {
    const lastMessage = state.messages[state.messages.length - 1] as MessageWithToolCalls;
    if (!lastMessage?.tool_calls?.length) {
      return END;
    }
    return "tools";
  } catch (error: unknown) {
    if (error instanceof Error) {
      throw new GraphExecutionError(error.message, "routeMessage");
    }
    throw new GraphExecutionError("Unknown error occurred", "routeMessage");
  }
} 