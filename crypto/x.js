fetch(`https://swtp771ld3.execute-api.us-east-1.amazonaws.com/default/aoz`,{
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        inputs: [
            messages
        ],
        parameters: {temperature:0.7}
    })
})