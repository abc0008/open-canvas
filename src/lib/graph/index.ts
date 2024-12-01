import { StateGraph, Annotation, START, END } from "@langchain/langgraph";
import { BaseMessage } from "@langchain/core/messages";
import { MemorySaver } from "@langchain/langgraph";
import { ChatOpenAI } from "@langchain/openai";
import { GraphState } from "./types";
import { routeMessage } from "./routing";

// Define model handlers
async function callModel(state: typeof GraphState.State) {
  const model = new ChatOpenAI({
    modelName: "gpt-4",
    temperature: 0
  });
  
  const response = await model.invoke(state.messages);
  return { messages: [response] };
}

async function toolNode(state: typeof GraphState.State) {
  // Implement tool execution logic
  const lastMessage = state.messages[state.messages.length - 1];
  // Add tool execution logic here
  return { messages: [] }; 
}

// Create graph with proper error handling
export function createGraph() {
  const memory = new MemorySaver();
  
  const workflow = new StateGraph(GraphState)
    .addNode("agent", callModel)
    .addNode("tools", toolNode)
    .addEdge(START, "agent")
    .addConditionalEdges("agent", routeMessage)
    .addEdge("tools", "agent");

  return workflow.compile({ 
    checkpointer: memory,
    interruptBefore: ["tools"]
  });
} 