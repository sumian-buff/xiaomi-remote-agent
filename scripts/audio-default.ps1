# Read / set the Windows default recording device (console + multimedia roles).
# The communications role is left alone so call apps keep using the headset mic.
if (-not ('MiVibeAudio.Default' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace MiVibeAudio {
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o);
    int OpenPropertyStore(int access, out IntPtr store);
    int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    int GetState(out int state);
  }
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int flow, int mask, out IntPtr devices);
    int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice device);
  }
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}
  [Guid("f8679f50-850a-41cf-9c72-430f290290c8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPolicyConfig {
    int GetMixFormat(); int GetDeviceFormat(); int ResetDeviceFormat(); int SetDeviceFormat();
    int GetProcessingPeriod(); int SetProcessingPeriod(); int GetShareMode(); int SetShareMode();
    int GetPropertyValue(); int SetPropertyValue();
    int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
    int SetEndpointVisibility();
  }
  [ComImport, Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")] class PolicyConfigClient {}
  public static class Default {
    public static string GetCapture() {
      var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
      IMMDevice d; Marshal.ThrowExceptionForHR(e.GetDefaultAudioEndpoint(1, 0, out d));
      string id; Marshal.ThrowExceptionForHR(d.GetId(out id)); return id;
    }
    public static void SetCapture(string id) {
      var p = (IPolicyConfig)new PolicyConfigClient();
      Marshal.ThrowExceptionForHR(p.SetDefaultEndpoint(id, 0));
      Marshal.ThrowExceptionForHR(p.SetDefaultEndpoint(id, 1));
    }
  }
}
'@
}

function Get-DefaultCaptureId { [MiVibeAudio.Default]::GetCapture() }
function Set-DefaultCaptureId([string]$Id) { [MiVibeAudio.Default]::SetCapture($Id) }

# Endpoint id of an active recording device whose name starts with $NamePrefix, e.g. "CABLE Output".
function Get-CaptureEndpointId([string]$NamePrefix) {
  $root = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture'
  foreach ($k in Get-ChildItem $root) {
    if ((Get-ItemProperty $k.PSPath).DeviceState -ne 1) { continue }
    $name = (Get-ItemProperty "$($k.PSPath)\Properties" -ErrorAction SilentlyContinue).'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
    if ($name -and $name.StartsWith($NamePrefix)) { return '{0.0.1.00000000}.' + $k.PSChildName }
  }
  return $null
}
