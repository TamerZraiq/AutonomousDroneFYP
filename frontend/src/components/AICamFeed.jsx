export default function AICamFeed() {
  const backendUrl = "http://172.20.10.3:8000/camera/stream"; 

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
