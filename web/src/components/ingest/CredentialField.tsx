"use client";

/**
 * CredentialField — env-var ref input with plaintext-storage banner.
 *
 * V1.5 stores credential refs as plain env-var names (per V1.5-R1 Q8 +
 * docs/12-security/v1.5-credentials.md). The banner per
 * 07-component-vocabulary.md §3 makes the policy visible at point of
 * entry.
 */

import { ShieldAlert } from "lucide-react";
import type { InputHTMLAttributes } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface CredentialFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  envVarRef: string;
  onEnvVarRefChange: (value: string) => void;
  id?: string;
  label?: string;
  helpText?: string;
}

export function CredentialField({
  envVarRef,
  onEnvVarRefChange,
  id = "credential-ref",
  label = "Credential env-var",
  helpText,
  className,
  ...inputProps
}: CredentialFieldProps) {
  const bannerId = `${id}-warning`;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={envVarRef}
        onChange={(e) => onEnvVarRefChange(e.target.value)}
        placeholder="MY_DB_PASSWORD"
        className="font-mono text-xs"
        aria-describedby={bannerId}
        autoComplete="off"
        {...inputProps}
      />
      <p
        id={bannerId}
        className="flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/5 px-2 py-1.5 text-[11px] text-warning"
      >
        <ShieldAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
        <span>
          V1.5 reads the secret from this env var on the SecBrain process. Stored
          in plaintext `.env`; V2 migrates to OS keychain.
          {helpText ? ` ${helpText}` : ""}
        </span>
      </p>
    </div>
  );
}
