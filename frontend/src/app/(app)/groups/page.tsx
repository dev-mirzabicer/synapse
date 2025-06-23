import { BrainCircuit } from "lucide-react";

export default function GroupsPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center bg-background rounded-lg m-2 border">
      <div className="text-center">
        <BrainCircuit className="mx-auto h-16 w-16 text-primary/70" />
        <h2 className="mt-6 text-2xl font-semibold tracking-tight">
          Welcome to SynapseUI
        </h2>
        <p className="mt-2 text-muted-foreground">
          Select a group from the sidebar to start chatting,
          <br /> or create a new group to begin a new collaboration.
        </p>
      </div>
    </div>
  );
}
