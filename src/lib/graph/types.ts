import { Annotation } from "@langchain/langgraph";
import { BaseMessage } from "@langchain/core/messages";
import { Tool } from "@langchain/core/tools";

// Define tool call interface since it's not exported directly
export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

// Extend BaseMessage to include tool_calls
export interface MessageWithToolCalls extends BaseMessage {
  tool_calls?: ToolCall[];
}

export const GraphState = Annotation.Root({
  messages: Annotation<MessageWithToolCalls[]>({
    reducer: (x, y) => x.concat(y),
  })
});

export type GraphStateType = typeof GraphState.State; 