cask "betterlanscan" do
  version "1.0.0"
  sha256 "4a189a9a7e5477dd59fa05bdb355ee29e45503b569cc4e1eee3f80f0705e7a38"

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
