function cloud9InstanceId() {
  jq -r ".Reservations[].Instances[] | select((.Tags[]|select(.Key==\"Name\")|.Value) | match(\"$user\") ) | .InstanceId"
}

# pass your username to get this to work
function cloud9Up() {
  user=${1-tsabat}
  aws --region us-west-2 ec2 start-instances --profile kicksaw --instance-id=$(
    aws --region us-west-2 ec2 describe-instances --profile kicksaw | cloud9InstanceId
  )
}
