param(
    [string]$Email = "admin@example.com",
    [string]$Password = "Llmops1234",
    [string]$Name = "Admin"
)

$ErrorActionPreference = "Stop"

if ($Password.Length -lt 8 -or $Password.Length -gt 16 -or $Password -notmatch "[A-Za-z]" -or $Password -notmatch "\d") {
    throw "Password must be 8-16 characters and contain at least one letter and one number."
}

$salt = New-Object byte[] 16
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($salt)
$rng.Dispose()

$pbkdf2 = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
    $Password,
    $salt,
    10000,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256
)
$hashBytes = $pbkdf2.GetBytes(32)
$hashHex = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
$passwordHash = [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($hashHex))
$passwordSalt = [Convert]::ToBase64String($salt)

$safeEmail = $Email.Replace("'", "''")
$safeName = $Name.Replace("'", "''")

$sql = @"
WITH updated AS (
  UPDATE account
  SET name = '$safeName',
      password = '$passwordHash',
      password_salt = '$passwordSalt'
  WHERE email = '$safeEmail'
  RETURNING id
)
INSERT INTO account (name, email, password, password_salt)
SELECT '$safeName', '$safeEmail', '$passwordHash', '$passwordSalt'
WHERE NOT EXISTS (SELECT 1 FROM updated);
"@

docker exec llmops-db psql -U postgres -d llmops -v ON_ERROR_STOP=1 -c $sql

$body = @{ email = $Email; password = $Password } | ConvertTo-Json
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:5011/auth/password-login" -Method Post -ContentType "application/json" -Body $body

if ($resp.code -ne "success") {
    throw "Account was written, but login verification failed: $($resp | ConvertTo-Json -Depth 5)"
}

Write-Host "Dev account is ready:"
Write-Host "  Email: $Email"
Write-Host "  Password: $Password"
