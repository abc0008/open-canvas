import { StreamEvent } from "@langchain/core/tracers/log_stream";

export async function streamGraph(graph: any, input: any, config: any) {
  const stream = await graph.streamEvents(
    input,
    {
      version: "v2",
      ...config
    },
    {
      includeNames: ["agent", "tools"] 
    }
  );

  for await (const event of stream) {
    // Handle different event types
    switch(event.event) {
      case "on_chain_start":
        // Handle chain start
        break;
      case "on_chain_end": 
        // Handle chain end
        break;
      default:
        // Handle other events
    }
  }
} 