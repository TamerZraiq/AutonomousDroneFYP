export default function DashboardCard({ title, children }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 flex flex-col gap-2 shadow-[0_0_40px_-10px_rgba(0,255,255,0.1)]">
      <div className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
        {title}
      </div>
      <div className="flex-1 flex justify-center items-center">
        {children}
      </div>
    </div>
  );
}
