import { BrainCircuit } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center bg-gray-100 dark:bg-gray-900 p-4">
       <div className="w-full max-w-md">
        <div className="flex justify-center items-center gap-2 mb-6">
            <BrainCircuit className="h-8 w-8 text-primary" />
            <h1 className="text-3xl font-bold text-primary font-headline">SynapseUI</h1>
        </div>
        {children}
       </div>
    </main>
  );
}
