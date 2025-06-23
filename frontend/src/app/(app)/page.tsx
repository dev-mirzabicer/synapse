"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// This page just redirects to the /groups page, which is the main app view.
export default function AppRootPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/groups");
  }, [router]);

  return null;
}
