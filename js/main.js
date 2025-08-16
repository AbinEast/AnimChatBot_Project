window.onload = function () {
    

// Variables
var messages = document.querySelector('.message-list')
var btn = document.querySelector('.btn')
var input = document.querySelector('input')

var volume = 1; // [Optional arg, can be null or empty] [0.0 - 1.0]
var expression = 4; // [Optional arg, can be null or empty] [index|name of expression]
var resetExpression = true; // [Optional arg, can be null or empty] [true|false] [default: true] [if true, expression will be reset to default after animation is over]
var crossOrigin = "anonymous"; // [Optional arg, to use not same-origin audios] [DEFAULT: null]
let model;

window.PIXI = PIXI;
const live2d = PIXI.live2d;

(async function () {
    let canvas_container = document.getElementById('canvas_container');
    const app = new PIXI.Application({
        view: document.getElementById('canvas'),
        autostart: true,

        height: canvas_container.offsetHeight,
        width: canvas_container.offsetWidth,
        backgroundAlpha: 0.0
    });
    //pilih pose
    model = await live2d.Live2DModel.from('static/model/kohane/09kohane_longunit_3_f_t04.model3.json', { autoInteract: false});

    app.stage.addChild(model);
    let scale = 1.5
    const scaleX = (canvas_container.offsetWidth)*scale / model.width;
    const scaleY = (canvas_container.offsetHeight)*scale / model.height;

    resize_factor = Math.min(scaleX, scaleY);

    // transforms
    model.x = -100;
    model.y = innerHeight+100;
    model.rotation = Math.PI;
    model.skew.x = Math.PI;
    model.scale.set(resize_factor);
    model.anchor.set(1, 1);
    model.motion("w-adult-glad01");
            
})();

function messageInteraction(audio_link, motion = NaN){
   model.speak(audio_link, {volume: volume,expression: expression,resetExpression: resetExpression,crossOrigin: crossOrigin});
}

// Button/Enter Key
btn.addEventListener('click', sendMessage)
input.addEventListener('keyup', function(e){ if(e.keyCode == 13) sendMessage() })

function loadHistory(){
    fetch('/history')
    .then(response => response.json())
    .then(data => {
        for (let i = 0; i < data.length; i++) {
            if (data[i].role == 'user') {
                writeLine(`<span>User</span><br> ${data[i].content}`,'primary')
            } else {
               writeLine(`<span>AKI</span><br> ${data[i].content}`, 'secondary')
            }
        }
    })
    .catch(error => console.error('Error:', error));
}

loadHistory()
// Messenger Functions
function sendMessage(){
   var msg = input.value;
   writeLine(`<span>User</span><br> ${msg}`,'primary')

   input.value = ''
   fetch('/chat', {
   method: 'POST',
   headers: {
       'Content-Type': 'application/json'
    },
   body: JSON.stringify({ 'message': msg })
       })
   .then(response => response.json())
   .then(data => addMessage(data, 'secondary'))
   .catch(error => console.error['Error:', error]);

}
function addMessage(msg, typeMessage = 'primary'){
   writeLine(`<span>${msg.FROM}</span><br> ${msg.MESSAGE}`,typeMessage)
   messageInteraction(msg.WAV, motion = NaN)
}
function writeLine(text, typeMessage){
   var message = document.createElement('li')
   message.classList.add('message-item', 'item-'+typeMessage)
   message.innerHTML = text
   messages.appendChild(message)
   messages.scrollTop = messages.scrollHeight;
}

}