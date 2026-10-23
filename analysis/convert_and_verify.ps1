Add-Type -AssemblyName System.Drawing

$captureDir = 'analysis\n10-gameplay'

$results = @()

foreach ($item in (Get-ChildItem -Path $captureDir -Filter '*.bmp' | Sort-Object LastWriteTime -Descending)) {
    $bmpPath = $item.FullName
    $pngName = $item.BaseName + '.png'
    $destPng = Join-Path $captureDir $pngName
    
    $bmp = [System.Drawing.Bitmap]::FromFile($bmpPath)
    $w = $bmp.Width
    $h = $bmp.Height
    $nonBlack = 0
    $total = 0
    $colorSums = @{ R = 0; G = 0; B = 0 }
    
    for ($x = 2; $x -le 98; $x += 4) {
        for ($y = 2; $y -le 98; $y += 4) {
            $px = [int]($w * $x / 100)
            $py = [int]($h * $y / 100)
            $c = $bmp.GetPixel($px, $py)
            $total++
            $colorSums.R += $c.R
            $colorSums.G += $c.G
            $colorSums.B += $c.B
            if ($c.R -gt 15 -or $c.G -gt 15 -or $c.B -gt 15) {
                $nonBlack++
            }
        }
    }
    
    $bmp.Save($destPng, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    
    $sha = (Get-FileHash -LiteralPath $destPng -Algorithm SHA256).Hash
    $size = (Get-Item -LiteralPath $destPng).Length
    $ratio = [Math]::Round(($nonBlack / [Math]::Max(1, $total)) * 100, 2)
    $avgR = [Math]::Round($colorSums.R / $total, 1)
    $avgG = [Math]::Round($colorSums.G / $total, 1)
    $avgB = [Math]::Round($colorSums.B / $total, 1)
    
    $status = if ($ratio -gt 10.0) { "VALID_RENDER" } elseif ($ratio -gt 1.0) { "PARTIAL_RENDER" } else { "MONOCHROME_BLACK" }

    $res = [PSCustomObject]@{
        Name = $pngName
        Resolution = "${w}x${h}"
        PngSize = $size
        NonBlackRatio = "${ratio}%"
        AvgRGB = "R=$avgR G=$avgG B=$avgB"
        Status = $status
        SHA256 = $sha
    }
    $results += $res
}

$results | Format-Table -AutoSize
