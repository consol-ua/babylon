import React from "react";
import { Activity } from "lucide-react";

interface VuMeterProps {
  label: string;
  volumeDb: number;
  isDucking?: boolean;
  activeColorClass?: string;
}

export const VuMeter: React.FC<VuMeterProps> = ({
  label,
  volumeDb,
  isDucking = false,
  activeColorClass = "bg-emerald-500",
}) => {
  // Normalize dB from [-60, 0] to [0, 100]%
  const volumePercentage = Math.max(
    0,
    Math.min(100, ((volumeDb + 60) / 60) * 100)
  );

  return (
    <div className="space-y-1.5 pt-1">
      <div className="flex justify-between items-center text-xs">
        <span className="text-slate-400 flex items-center gap-1">
          <Activity className="w-3.5 h-3.5 text-indigo-400" />
          {label}
        </span>
        <span className="font-mono text-slate-400 text-[11px]">
          {volumeDb.toFixed(1)} dB
        </span>
      </div>
      <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
        <div
          className={`h-full transition-all duration-75 ${
            isDucking ? "bg-amber-500" : activeColorClass
          }`}
          style={{ width: `${volumePercentage}%` }}
        />
      </div>
      {isDucking && (
        <span className="text-[10px] text-amber-400 font-semibold tracking-wider uppercase block">
          Ducking активний (лунає переклад)
        </span>
      )}
    </div>
  );
};
