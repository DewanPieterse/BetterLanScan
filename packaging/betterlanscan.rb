cask "betterlanscan" do
  version "1.1.0"
  sha256 "0b0af79d9b3d8db8b5d12badb2e0d52e5584c1ba07d3c355f851d49df3dd9261"

  url "https://github.com/DewanPieterse/BetterLanScan/releases/download/v#{version}/BetterLanScan-#{version}.zip"
  name "BetterLanScan"
  desc "Scans the local network for devices and surveys nearby Wi-Fi networks"
  homepage "https://github.com/DewanPieterse/BetterLanScan"

  # Ad-hoc signed (not notarized); Gatekeeper shows an "unidentified developer"
  # prompt on first launch — right-click ▸ Open, or System Settings ▸ Privacy
  # & Security ▸ Open Anyway. Install with --no-quarantine to skip the prompt:
  #   brew install --cask --no-quarantine betterlanscan
  depends_on macos: ">= :big_sur"

  app "BetterLanScan.app"

  zap trash: [
    "~/Library/Application Support/BetterLanScan",
  ]
end
