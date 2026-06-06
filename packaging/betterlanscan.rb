cask "betterlanscan" do
  version "1.0.1"
  sha256 "9fac51a164b50391ea21d2363d22b0eaafd9b6859ebf269b676175d2941ec3e7"

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
