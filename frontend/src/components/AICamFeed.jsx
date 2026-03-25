export default function AICamFeed() { 
  const backendUrl = "/camera/stream"; 

  return (
    <div className="flex justify-center items-center w-full h-full">
      <img
        src={backendUrl}
        alt="AI Camera Live Feed"
        className="rounded-lg shadow-lg max-h-80 object-contain"
        style={{ borderRadius: "10px" }}
      />
    </div>
  );
}
