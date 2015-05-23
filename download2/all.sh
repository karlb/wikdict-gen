DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
set -x  # print commands
$DIR/download.py $1 $2
$DIR/download.py $2 $1
$DIR/group.py $1 $2
