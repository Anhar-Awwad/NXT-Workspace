# Auto-detect the public IP of whoever runs terraform apply.
data "http" "my_ip" {
  url = "https://api.ipify.org"
}